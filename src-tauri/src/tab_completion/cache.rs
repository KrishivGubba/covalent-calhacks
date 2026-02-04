use anyhow::Result;
use lru::LruCache;
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::num::NonZeroUsize;
use std::sync::{Arc, RwLock};
use std::time::{SystemTime, UNIX_EPOCH};
use super::graph_db::GraphDatabase;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CachedContext {
    pub app_context: AppContext,
    pub activity_type: ActivityType,
    pub learned_patterns: Vec<Pattern>,
    pub recent_actions: Vec<String>,
    pub screen_context: Option<String>, // OCR or visible text from screen
    pub timestamp: u64,
    pub ttl: u64,
    /// Context chain information for tracking related contexts
    #[serde(default)]
    pub context_chain: Option<ContextChainInfo>,
}

/// Information about the current context chain for prompt inclusion
#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct ContextChainInfo {
    /// Chain ID grouping related contexts
    pub chain_id: String,
    /// Formatted summary for prompt inclusion
    pub chain_summary: String,
    /// Brief descriptions of related contexts
    pub related_contexts: Vec<String>,
    /// Number of contexts in this chain
    pub chain_length: usize,
    /// Whether this is a new chain (antichain detected)
    pub is_new_chain: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AppContext {
    pub name: String,
    pub bundle_id: String,
    pub window_title: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum ActivityType {
    Terminal { shell: String, cwd: String },
    Browser { domain: String, page_type: String },
    Code { language: String, file_type: String },
    NativeText { app_name: String },
    Unknown,
}

impl ActivityType {
    pub fn from_app(app_name: &str) -> Self {
        if app_name.contains("Terminal") || app_name.contains("iTerm") {
            ActivityType::Terminal {
                shell: "zsh".to_string(),
                cwd: String::new(),
            }
        } else if app_name.contains("Chrome") || app_name.contains("Safari") {
            ActivityType::Browser {
                domain: String::new(),
                page_type: "generic_web".to_string(),
            }
        } else if app_name.contains("Code") || app_name.contains("Xcode") {
            ActivityType::Code {
                language: "unknown".to_string(),
                file_type: String::new(),
            }
        } else {
            ActivityType::NativeText {
                app_name: app_name.to_string(),
            }
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Pattern {
    pub trigger: String,
    pub completion: String,
    pub confidence: f64,
    pub use_count: usize,
}

pub struct MultiTierCache {
    // L0: Exact prediction cache
    exact_cache: Arc<RwLock<LruCache<String, String>>>,

    // L1: Context cache by app + activity
    context_cache: Arc<RwLock<LruCache<String, CachedContext>>>,

    // L2: Direct SQLite access to graph.db
    graph_db: Option<Arc<GraphDatabase>>,

    // Stats for monitoring
    stats: Arc<RwLock<CacheStats>>,

    // Usage tracking for adaptive TTL
    usage_patterns: Arc<RwLock<HashMap<String, UsagePattern>>>,
}

#[derive(Default, Debug, Clone)]
pub struct CacheStats {
    pub l0_hits: usize,
    pub l0_misses: usize,
    pub l1_hits: usize,
    pub l1_misses: usize,
    pub l2_hits: usize,
    pub l2_misses: usize,
    pub l3_calls: usize,
}

#[derive(Debug, Clone)]
struct UsagePattern {
    access_count: usize,
    last_access: u64,
    hit_rate: f64,
}

#[derive(Debug)]
pub enum CacheResult {
    ExactHit(String),           // L0: Return prediction directly
    ContextHit(CachedContext),  // L1: Use cached context
    GraphHit(CachedContext),    // L2: Reconstructed from graph
    NeedExtraction,             // L3: Must extract fresh context
}

impl MultiTierCache {
    pub fn new(graph_db_path: String) -> Self {
        println!("📦 Initializing multi-tier cache system");

        // Try to connect to graph.db directly
        let graph_db = match GraphDatabase::new(graph_db_path.clone()) {
            Ok(db) => {
                println!("✅ Connected to graph.db directly at: {}", graph_db_path);
                if let Ok(stats) = db.get_stats() {
                    println!("   📊 Graph stats: {} nodes, {} data entries, {} actions",
                             stats.node_count, stats.data_count, stats.action_count);
                }
                Some(Arc::new(db))
            }
            Err(e) => {
                eprintln!("⚠️  Failed to connect to graph.db: {}", e);
                eprintln!("   Will use Flask API fallback");
                None
            }
        };

        Self {
            exact_cache: Arc::new(RwLock::new(LruCache::new(
                NonZeroUsize::new(1000).unwrap()
            ))),
            context_cache: Arc::new(RwLock::new(LruCache::new(
                NonZeroUsize::new(100).unwrap()
            ))),
            graph_db,
            stats: Arc::new(RwLock::new(CacheStats::default())),
            usage_patterns: Arc::new(RwLock::new(HashMap::new())),
        }
    }
    
    /// Main lookup: tries L0 → L1 → L2 → L3
    pub fn get_prediction_or_context(
        &self,
        app_name: &str,
        text: &str,
        current_activity_id: &str,
    ) -> CacheResult {
        
        // L0: Try exact match first
        let exact_key = format!("{}:{}", app_name, text);
        if let Some(prediction) = self.exact_cache.write().unwrap().get(&exact_key) {
            self.stats.write().unwrap().l0_hits += 1;
            println!("⚡ L0 cache hit!");
            return CacheResult::ExactHit(prediction.clone());
        }
        self.stats.write().unwrap().l0_misses += 1;
        
        // L1: Try context cache
        let context_key = format!("{}:{}", app_name, current_activity_id);
        if let Some(context) = self.context_cache.write().unwrap().get(&context_key) {
            if !context.is_stale() {
                self.stats.write().unwrap().l1_hits += 1;
                println!("💾 L1 cache hit!");
                return CacheResult::ContextHit(context.clone());
            }
        }
        self.stats.write().unwrap().l1_misses += 1;
        
        // L2: Try graph reconstruction
        if let Some(context) = self.reconstruct_from_graph(app_name, current_activity_id) {
            // Cache it for next time
            self.context_cache.write().unwrap().put(context_key, context.clone());
            self.stats.write().unwrap().l2_hits += 1;
            println!("🔍 L2 graph hit!");
            return CacheResult::GraphHit(context);
        }
        self.stats.write().unwrap().l2_misses += 1;
        
        // L3: Need full extraction
        self.stats.write().unwrap().l3_calls += 1;
        println!("🆕 L3 full extraction needed");
        CacheResult::NeedExtraction
    }
    
    fn reconstruct_from_graph(&self, app_name: &str, activity_id: &str) -> Option<CachedContext> {
        // Use direct SQLite access to query graph.db
        if let Some(ref graph_db) = self.graph_db {
            // Query graph for relevant context
            let query = format!("App: {} Activity: {}", app_name, activity_id);

            match graph_db.search_nodes(&query, 5) {
                Ok(nodes) if !nodes.is_empty() => {
                    let activity_type = ActivityType::from_app(app_name);

                    // Extract learned patterns from graph nodes
                    let mut learned_patterns = Vec::new();
                    let mut recent_actions = Vec::new();

                    for node in &nodes {
                        // Use data entries as patterns
                        for data_entry in &node.data_entries {
                            if let Some(ref key) = data_entry.key {
                                recent_actions.push(key.clone());
                            }

                            // Try to extract patterns from info
                            if data_entry.info.len() < 200 {
                                recent_actions.push(data_entry.info.clone());
                            }
                        }
                    }

                    recent_actions.truncate(10);

                    return Some(CachedContext {
                        app_context: AppContext {
                            name: app_name.to_string(),
                            bundle_id: String::new(),
                            window_title: None,
                        },
                        activity_type,
                        learned_patterns,
                        recent_actions,
                        screen_context: None,
                        timestamp: current_timestamp(),
                        ttl: 300,
                        context_chain: None,
                    });
                }
                Ok(_) => {
                    // No nodes found, try getting recent nodes
                    if let Ok(recent_nodes) = graph_db.get_recent_nodes(3) {
                        if !recent_nodes.is_empty() {
                            let activity_type = ActivityType::from_app(app_name);
                            let mut recent_actions = Vec::new();

                            for node in &recent_nodes {
                                for data_entry in &node.data_entries {
                                    if let Some(ref key) = data_entry.key {
                                        recent_actions.push(key.clone());
                                    }
                                }
                            }

                            recent_actions.truncate(5);

                            return Some(CachedContext {
                                app_context: AppContext {
                                    name: app_name.to_string(),
                                    bundle_id: String::new(),
                                    window_title: None,
                                },
                                activity_type,
                                learned_patterns: vec![],
                                recent_actions,
                                screen_context: None,
                                timestamp: current_timestamp(),
                                ttl: 300,
                                context_chain: None,
                            });
                        }
                    }
                }
                Err(e) => {
                    eprintln!("⚠️  Graph query error: {}", e);
                }
            }
        }

        // Fallback: create basic context
        let activity_type = ActivityType::from_app(app_name);
        Some(CachedContext {
            app_context: AppContext {
                name: app_name.to_string(),
                bundle_id: String::new(),
                window_title: None,
            },
            activity_type,
            learned_patterns: vec![],
            recent_actions: vec![],
            screen_context: None,
            timestamp: current_timestamp(),
            ttl: 300,
            context_chain: None,
        })
    }
    
    pub fn cache_prediction(&self, app_name: &str, text: &str, prediction: &str) {
        let key = format!("{}:{}", app_name, text);
        self.exact_cache.write().unwrap().put(key, prediction.to_string());
    }
    
    pub fn cache_context(&self, app_name: &str, activity_id: &str, mut context: CachedContext) {
        let key = format!("{}:{}", app_name, activity_id);
        
        // Apply adaptive TTL based on usage patterns
        context.ttl = self.calculate_adaptive_ttl(&key, context.ttl);
        
        // Track usage
        self.record_access(&key);
        
        self.context_cache.write().unwrap().put(key, context);
    }
    
    /// Get context from cache if available
    pub fn get_context(&self, app_name: &str, activity_id: &str) -> Option<CachedContext> {
        let key = format!("{}:{}", app_name, activity_id);
        self.context_cache.write().unwrap().get(&key).cloned()
    }
    
    /// Calculate adaptive TTL based on usage patterns
    /// More frequently accessed contexts get longer TTLs
    fn calculate_adaptive_ttl(&self, key: &str, default_ttl: u64) -> u64 {
        let patterns = self.usage_patterns.read().unwrap();
        
        if let Some(pattern) = patterns.get(key) {
            // If access count is high and hit rate is good, increase TTL
            if pattern.access_count > 10 && pattern.hit_rate > 0.7 {
                // Increase TTL by up to 2x for hot patterns
                let multiplier = 1.0 + (pattern.hit_rate * pattern.access_count as f64 / 100.0).min(1.0);
                (default_ttl as f64 * multiplier) as u64
            } else if pattern.hit_rate < 0.3 {
                // Decrease TTL for cold patterns
                (default_ttl as f64 * 0.7) as u64
            } else {
                default_ttl
            }
        } else {
            default_ttl
        }
    }
    
    /// Record access for adaptive TTL calculation
    fn record_access(&self, key: &str) {
        let mut patterns = self.usage_patterns.write().unwrap();
        
        let now = current_timestamp();
        let pattern = patterns.entry(key.to_string()).or_insert(UsagePattern {
            access_count: 0,
            last_access: now,
            hit_rate: 0.5, // Start with neutral hit rate
        });
        
        pattern.access_count += 1;
        pattern.last_access = now;
        
        // Update hit rate based on cache stats
        let stats = self.stats.read().unwrap();
        let total_hits = stats.l0_hits + stats.l1_hits + stats.l2_hits;
        let total_requests = total_hits + stats.l0_misses + stats.l1_misses + stats.l2_misses + stats.l3_calls;
        
        if total_requests > 0 {
            pattern.hit_rate = total_hits as f64 / total_requests as f64;
        }
    }
    
    pub fn print_stats(&self) {
        let stats = self.stats.read().unwrap();
        let total_l0 = stats.l0_hits + stats.l0_misses;
        let total_l1 = stats.l1_hits + stats.l1_misses;
        let total_l2 = stats.l2_hits + stats.l2_misses;
        
        println!("\n📊 Cache Statistics:");
        if total_l0 > 0 {
            println!("  L0 hits: {} / {} ({:.1}%)", 
                stats.l0_hits, total_l0,
                stats.l0_hits as f64 / total_l0 as f64 * 100.0
            );
        }
        if total_l1 > 0 {
            println!("  L1 hits: {} / {} ({:.1}%)", 
                stats.l1_hits, total_l1,
                stats.l1_hits as f64 / total_l1 as f64 * 100.0
            );
        }
        if total_l2 > 0 {
            println!("  L2 hits: {} / {} ({:.1}%)", 
                stats.l2_hits, total_l2,
                stats.l2_hits as f64 / total_l2 as f64 * 100.0
            );
        }
        println!("  L3 calls: {}\n", stats.l3_calls);
    }
    
    pub fn on_app_switch(&self, _old_app: &str, _new_app: &str) {
        // Context cache uses activity_id, so switches are handled automatically
        println!("🔄 App switch detected");
    }
    
    pub fn on_activity_change(&self, _app: &str, _new_activity_type: ActivityType) {
        // Could implement smart invalidation here
        // For now, let TTLs handle it
        println!("🔄 Activity change detected");
    }
    
    /// Evict least recently used entries to keep cache size manageable
    pub fn evict_lru(&self) {
        let exact_size = self.exact_cache.read().unwrap().len();
        let context_size = self.context_cache.read().unwrap().len();
        
        println!("📊 Cache sizes - L0: {}, L1: {}", exact_size, context_size);
        
        // LRU cache handles eviction automatically when size limit is reached
    }
    
    /// Get detailed statistics
    pub fn get_detailed_stats(&self) -> CacheStats {
        self.stats.read().unwrap().clone()
    }
    
    /// Print a visual representation of the current cache state
    pub fn visualize(&self) {
        let stats = self.stats.read().unwrap();
        let exact_size = self.exact_cache.read().unwrap().len();
        let context_size = self.context_cache.read().unwrap().len();
        
        // Calculate hit rates
        let l0_total = stats.l0_hits + stats.l0_misses;
        let l1_total = stats.l1_hits + stats.l1_misses;
        let l2_total = stats.l2_hits + stats.l2_misses;
        
        let l0_rate = if l0_total > 0 { stats.l0_hits as f64 / l0_total as f64 } else { 0.0 };
        let l1_rate = if l1_total > 0 { stats.l1_hits as f64 / l1_total as f64 } else { 0.0 };
        let l2_rate = if l2_total > 0 { stats.l2_hits as f64 / l2_total as f64 } else { 0.0 };
        
        fn make_bar(value: usize, max: usize, width: usize) -> String {
            let filled = if max > 0 { (value * width) / max } else { 0 };
            let empty = width.saturating_sub(filled);
            format!("[{}{}]", "█".repeat(filled), "░".repeat(empty))
        }
        
        println!("\n╔══════════════════════════════════════════════════════════════╗");
        println!("║            📦 TAB COMPLETION CACHE STATE                     ║");
        println!("╠══════════════════════════════════════════════════════════════╣");
        
        // L0 - Exact Cache
        println!("║                                                              ║");
        println!("║  ┌─────────────────────────────────────────────────────────┐ ║");
        println!("║  │ L0: EXACT PREDICTIONS                                   │ ║");
        println!("║  │ ════════════════════                                    │ ║");
        println!("║  │ Entries: {:>4} / 1000  {}                     │ ║", 
            exact_size, 
            make_bar(exact_size, 1000, 20)
        );
        println!("║  │ Hit Rate: {:>5.1}%      {}                     │ ║",
            l0_rate * 100.0,
            make_bar((l0_rate * 100.0) as usize, 100, 20)
        );
        println!("║  │ Hits: {:>5}  Misses: {:>5}                              │ ║",
            stats.l0_hits, stats.l0_misses
        );
        println!("║  └─────────────────────────────────────────────────────────┘ ║");
        
        // L1 - Context Cache
        println!("║                          ↓                                   ║");
        println!("║  ┌─────────────────────────────────────────────────────────┐ ║");
        println!("║  │ L1: CONTEXT CACHE                                       │ ║");
        println!("║  │ ═══════════════════                                     │ ║");
        println!("║  │ Entries: {:>4} / 100   {}                     │ ║",
            context_size,
            make_bar(context_size, 100, 20)
        );
        println!("║  │ Hit Rate: {:>5.1}%      {}                     │ ║",
            l1_rate * 100.0,
            make_bar((l1_rate * 100.0) as usize, 100, 20)
        );
        println!("║  │ Hits: {:>5}  Misses: {:>5}                              │ ║",
            stats.l1_hits, stats.l1_misses
        );
        println!("║  └─────────────────────────────────────────────────────────┘ ║");
        
        // L2 - Graph DB
        println!("║                          ↓                                   ║");
        println!("║  ┌─────────────────────────────────────────────────────────┐ ║");
        println!("║  │ L2: GRAPH DATABASE                                      │ ║");
        println!("║  │ ═══════════════════                                     │ ║");
        println!("║  │ Status: {}                                    │ ║",
            if self.graph_db.is_some() { "🟢 Connected  " } else { "🔴 Disconnected" }
        );
        println!("║  │ Hit Rate: {:>5.1}%      {}                     │ ║",
            l2_rate * 100.0,
            make_bar((l2_rate * 100.0) as usize, 100, 20)
        );
        println!("║  │ Hits: {:>5}  Misses: {:>5}                              │ ║",
            stats.l2_hits, stats.l2_misses
        );
        println!("║  └─────────────────────────────────────────────────────────┘ ║");
        
        // L3 - Full Extraction
        println!("║                          ↓                                   ║");
        println!("║  ┌─────────────────────────────────────────────────────────┐ ║");
        println!("║  │ L3: FULL EXTRACTION (Fallback)                          │ ║");
        println!("║  │ ═══════════════════════════════                         │ ║");
        println!("║  │ Calls: {:>5}                                            │ ║",
            stats.l3_calls
        );
        println!("║  └─────────────────────────────────────────────────────────┘ ║");
        
        // Overall stats
        let total_requests = l0_total;
        let total_hits = stats.l0_hits + stats.l1_hits + stats.l2_hits;
        let overall_rate = if total_requests > 0 { 
            total_hits as f64 / total_requests as f64 
        } else { 0.0 };
        
        println!("║                                                              ║");
        println!("╠══════════════════════════════════════════════════════════════╣");
        println!("║  OVERALL: {:>5} requests, {:>5.1}% served from cache         ║",
            total_requests, overall_rate * 100.0
        );
        println!("╚══════════════════════════════════════════════════════════════╝\n");
    }
    
    /// Get cache state as JSON for external tools
    pub fn get_state_json(&self) -> String {
        let stats = self.stats.read().unwrap();
        let exact_size = self.exact_cache.read().unwrap().len();
        let context_size = self.context_cache.read().unwrap().len();
        
        format!(r#"{{
  "l0": {{ "size": {}, "max": 1000, "hits": {}, "misses": {} }},
  "l1": {{ "size": {}, "max": 100, "hits": {}, "misses": {} }},
  "l2": {{ "connected": {}, "hits": {}, "misses": {} }},
  "l3": {{ "calls": {} }}
}}"#,
            exact_size, stats.l0_hits, stats.l0_misses,
            context_size, stats.l1_hits, stats.l1_misses,
            self.graph_db.is_some(), stats.l2_hits, stats.l2_misses,
            stats.l3_calls
        )
    }
}

impl CachedContext {
    pub fn is_stale(&self) -> bool {
        current_timestamp() - self.timestamp > self.ttl
    }
}

pub fn current_timestamp() -> u64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap()
        .as_secs()
}

#[cfg(test)]
mod tests {
    use super::*;
    
    #[test]
    fn test_cache_creation() {
        let cache = MultiTierCache::new("test.db".to_string());
        let result = cache.get_prediction_or_context("Terminal", "git co", "test_activity");
        assert!(matches!(result, CacheResult::NeedExtraction));
    }
    
    #[test]
    fn test_cache_l0_hit() {
        let cache = MultiTierCache::new("test.db".to_string());
        cache.cache_prediction("Terminal", "git co", "mmit -m ''");
        
        let result = cache.get_prediction_or_context("Terminal", "git co", "test_activity");
        assert!(matches!(result, CacheResult::ExactHit(_)));
    }
}

