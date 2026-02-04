//! Context Memory System
//!
//! Maintains a rolling history of recent contexts (10-15 entries) with
//! relevancy + recency scoring. Detects context chains (related actions)
//! vs antichains (unrelated new tasks).

use anyhow::Result;
use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use std::collections::{HashMap, HashSet, VecDeque};
use std::sync::Arc;
use tokio::sync::RwLock;
use uuid::Uuid;

use crate::screen_context::context_data::{ActivityLevel, RawContext};
use crate::screen_context::context_type::ContextType;

/// Maximum number of contexts to retain in memory
const DEFAULT_MAX_SIZE: usize = 15;

/// Default similarity threshold for chain continuation (0.0-1.0)
const DEFAULT_CHAIN_SIMILARITY_THRESHOLD: f32 = 0.4;

/// Default time threshold for automatic chain break (seconds)
const DEFAULT_CHAIN_TIME_THRESHOLD: u64 = 300; // 5 minutes

/// Default recency decay half-life (seconds)
const DEFAULT_RECENCY_HALF_LIFE: f64 = 120.0; // 2 minutes

// ============================================================================
// Data Structures
// ============================================================================

/// Lightweight summary of a context snapshot for efficient storage and comparison
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ContextSummary {
    /// Unique identifier for this context snapshot
    pub id: String,

    /// Chain ID - contexts in the same chain share this ID
    pub chain_id: String,

    /// Application name (e.g., "VSCode", "Chrome")
    pub app_name: String,

    /// Application bundle ID for more precise matching
    pub bundle_id: String,

    /// Window title at capture time
    pub window_title: Option<String>,

    /// Detected context type
    pub context_type: ContextType,

    /// Confidence score from context detection (0.0-1.0)
    pub context_confidence: f32,

    /// Timestamp when this context was captured
    pub timestamp: DateTime<Utc>,

    /// Tags for similarity matching
    pub tags: HashSet<String>,

    /// Short description/summary (optional, from LLM analysis)
    pub description: Option<String>,

    /// Activity level at capture time
    pub activity_level: ActivityLevel,

    /// Key indicators extracted from context (URLs, file paths, etc.)
    pub key_indicators: Vec<String>,

    /// Duration spent in this context (updated on context switch)
    pub duration_secs: u64,
}

/// Result of querying context memory for relevant contexts
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ContextChainResult {
    /// Ordered list of relevant contexts (most relevant first)
    pub contexts: Vec<ScoredContext>,

    /// Current chain ID
    pub chain_id: String,

    /// Whether a new chain was detected (antichain)
    pub is_new_chain: bool,

    /// Chain statistics
    pub chain_stats: ChainStats,
}

/// A context with its computed scores
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ScoredContext {
    pub summary: ContextSummary,
    pub relevancy_score: f32,
    pub recency_score: f32,
    pub combined_score: f32,
    pub is_same_chain: bool,
}

/// Statistics about a context chain
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ChainStats {
    pub chain_length: usize,
    pub chain_duration_secs: u64,
    pub dominant_context_type: String,
    pub app_diversity: usize,
}

/// Decision about whether to continue a chain or start a new one
#[derive(Debug, Clone)]
pub enum ChainDecision {
    /// Continue current chain - context is related
    ContinueChain { chain_id: String, similarity_score: f32 },
    /// Start new chain - context is unrelated (antichain detected)
    NewChain {
        new_chain_id: String,
        reason: AntichainReason,
    },
}

/// Reason for starting a new chain (antichain detection)
#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum AntichainReason {
    /// Similarity below threshold
    LowSimilarity { score: f32, threshold: f32 },
    /// Too much time has passed
    TimeGap { seconds: u64, threshold: u64 },
    /// Major app category change
    CategoryChange { from: String, to: String },
    /// First context (no history)
    FirstContext,
    /// Manual chain break
    Manual,
}

/// Statistics about the context memory
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct ContextMemoryStats {
    pub total_contexts: usize,
    pub total_chains: usize,
    pub current_chain_length: usize,
    pub oldest_context_age_secs: u64,
    pub average_similarity: f32,
}

// ============================================================================
// ContextMemory Implementation
// ============================================================================

/// Main context memory manager - stores and retrieves context history
pub struct ContextMemory {
    /// Ring buffer of context summaries
    summaries: Arc<RwLock<VecDeque<ContextSummary>>>,

    /// Maximum number of contexts to retain
    max_size: usize,

    /// Current active chain ID
    current_chain_id: Arc<RwLock<String>>,

    /// Chain history - maps chain IDs to their context summary IDs
    chains: Arc<RwLock<HashMap<String, Vec<String>>>>,

    /// Similarity threshold for chain continuation (0.0-1.0)
    chain_similarity_threshold: f32,

    /// Time threshold for automatic chain break (seconds)
    chain_time_threshold: u64,

    /// Recency decay half-life (seconds) for scoring
    recency_half_life: f64,
}

impl ContextMemory {
    /// Create a new context memory with default settings
    pub fn new() -> Self {
        let initial_chain_id = Self::generate_chain_id();
        Self {
            summaries: Arc::new(RwLock::new(VecDeque::with_capacity(DEFAULT_MAX_SIZE))),
            max_size: DEFAULT_MAX_SIZE,
            current_chain_id: Arc::new(RwLock::new(initial_chain_id.clone())),
            chains: Arc::new(RwLock::new(HashMap::new())),
            chain_similarity_threshold: DEFAULT_CHAIN_SIMILARITY_THRESHOLD,
            chain_time_threshold: DEFAULT_CHAIN_TIME_THRESHOLD,
            recency_half_life: DEFAULT_RECENCY_HALF_LIFE,
        }
    }

    /// Set maximum number of contexts to retain
    pub fn with_max_size(mut self, size: usize) -> Self {
        self.max_size = size;
        self
    }

    /// Set similarity threshold for chain continuation
    pub fn with_chain_threshold(mut self, threshold: f32) -> Self {
        self.chain_similarity_threshold = threshold;
        self
    }

    /// Set time threshold for automatic chain break
    pub fn with_time_threshold(mut self, seconds: u64) -> Self {
        self.chain_time_threshold = seconds;
        self
    }

    /// Set recency decay half-life
    pub fn with_recency_half_life(mut self, seconds: f64) -> Self {
        self.recency_half_life = seconds;
        self
    }

    // ========================================================================
    // Core Operations
    // ========================================================================

    /// Add a new context to memory, returns chain analysis result
    pub async fn add_context(&self, context: &RawContext) -> Result<ContextChainResult> {
        // Create summary from raw context
        let chain_id = self.current_chain_id.read().await.clone();
        let mut summary = self.summarize_context(context, chain_id.clone());

        // Detect if this is a chain continuation or new chain
        let decision = self.detect_chain_or_antichain(&summary).await;
        let is_new_chain = matches!(decision, ChainDecision::NewChain { .. });

        // Update chain ID based on decision
        match &decision {
            ChainDecision::ContinueChain { chain_id, .. } => {
                summary.chain_id = chain_id.clone();
            }
            ChainDecision::NewChain { new_chain_id, .. } => {
                summary.chain_id = new_chain_id.clone();
                *self.current_chain_id.write().await = new_chain_id.clone();
            }
        }

        // Update duration of previous context in same chain
        {
            let mut summaries = self.summaries.write().await;
            if let Some(prev) = summaries.back_mut() {
                if prev.chain_id == summary.chain_id {
                    let duration = (summary.timestamp - prev.timestamp)
                        .num_seconds()
                        .max(0) as u64;
                    prev.duration_secs = duration;
                }
            }

            // Add to ring buffer, evicting oldest if full
            if summaries.len() >= self.max_size {
                summaries.pop_front();
            }
            summaries.push_back(summary.clone());
        }

        // Update chain mapping
        {
            let mut chains = self.chains.write().await;
            chains
                .entry(summary.chain_id.clone())
                .or_insert_with(Vec::new)
                .push(summary.id.clone());
        }

        // Build result
        self.get_relevant_contexts(context, self.max_size).await
    }

    /// Get relevant contexts for the current situation
    pub async fn get_relevant_contexts(
        &self,
        current_context: &RawContext,
        limit: usize,
    ) -> Result<ContextChainResult> {
        let current_chain_id = self.current_chain_id.read().await.clone();
        let current_summary =
            self.summarize_context(current_context, current_chain_id.clone());

        let summaries = self.summaries.read().await;

        // Score all contexts
        let mut scored: Vec<ScoredContext> = summaries
            .iter()
            .map(|ctx| self.calculate_combined_score(ctx, &current_summary))
            .collect();

        // Sort by combined score (descending)
        scored.sort_by(|a, b| {
            b.combined_score
                .partial_cmp(&a.combined_score)
                .unwrap_or(std::cmp::Ordering::Equal)
        });

        // Limit results
        scored.truncate(limit);

        // Calculate chain stats
        let chain_stats = self.calculate_chain_stats(&current_chain_id, &summaries);

        Ok(ContextChainResult {
            contexts: scored,
            chain_id: current_chain_id,
            is_new_chain: false, // This is a query, not an add
            chain_stats,
        })
    }

    /// Get the current context chain (related contexts)
    pub async fn get_current_chain(&self) -> Result<Vec<ContextSummary>> {
        let chain_id = self.current_chain_id.read().await.clone();
        self.get_chain(&chain_id).await
    }

    /// Get contexts from a specific chain by ID
    pub async fn get_chain(&self, chain_id: &str) -> Result<Vec<ContextSummary>> {
        let summaries = self.summaries.read().await;
        let chain_contexts: Vec<ContextSummary> = summaries
            .iter()
            .filter(|ctx| ctx.chain_id == chain_id)
            .cloned()
            .collect();
        Ok(chain_contexts)
    }

    // ========================================================================
    // Chain Management
    // ========================================================================

    /// Detect if current context is a chain continuation or new chain
    pub async fn detect_chain_or_antichain(&self, current: &ContextSummary) -> ChainDecision {
        let summaries = self.summaries.read().await;

        // Get most recent context
        let recent = match summaries.back() {
            Some(ctx) => ctx,
            None => {
                // No history, start first chain
                return ChainDecision::NewChain {
                    new_chain_id: Self::generate_chain_id(),
                    reason: AntichainReason::FirstContext,
                };
            }
        };

        // Check time gap
        let time_gap = (current.timestamp - recent.timestamp)
            .num_seconds()
            .max(0) as u64;
        if time_gap > self.chain_time_threshold {
            return ChainDecision::NewChain {
                new_chain_id: Self::generate_chain_id(),
                reason: AntichainReason::TimeGap {
                    seconds: time_gap,
                    threshold: self.chain_time_threshold,
                },
            };
        }

        // Check context type category change
        let current_category = Self::get_category_name(&current.context_type);
        let recent_category = Self::get_category_name(&recent.context_type);

        if current_category != recent_category {
            // Check if contexts are related (allow some transitions)
            if !Self::are_categories_related(&current_category, &recent_category) {
                return ChainDecision::NewChain {
                    new_chain_id: Self::generate_chain_id(),
                    reason: AntichainReason::CategoryChange {
                        from: recent_category.to_string(),
                        to: current_category.to_string(),
                    },
                };
            }
        }

        // Calculate similarity
        let similarity = Self::calculate_similarity(recent, current);
        if similarity < self.chain_similarity_threshold {
            return ChainDecision::NewChain {
                new_chain_id: Self::generate_chain_id(),
                reason: AntichainReason::LowSimilarity {
                    score: similarity,
                    threshold: self.chain_similarity_threshold,
                },
            };
        }

        // Continue current chain
        ChainDecision::ContinueChain {
            chain_id: recent.chain_id.clone(),
            similarity_score: similarity,
        }
    }

    /// Force start a new chain (manual chain break)
    pub async fn start_new_chain(&self) -> String {
        let new_chain_id = Self::generate_chain_id();
        *self.current_chain_id.write().await = new_chain_id.clone();
        new_chain_id
    }

    // ========================================================================
    // Similarity & Scoring
    // ========================================================================

    /// Calculate similarity between two context summaries (0.0-1.0)
    pub fn calculate_similarity(a: &ContextSummary, b: &ContextSummary) -> f32 {
        // Weights for different factors
        const CONTEXT_TYPE_WEIGHT: f32 = 0.35;
        const APP_WEIGHT: f32 = 0.25;
        const TAG_WEIGHT: f32 = 0.25;
        const INDICATOR_WEIGHT: f32 = 0.15;

        // 1. Context Type Match
        let context_type_score = Self::context_type_similarity(&a.context_type, &b.context_type);

        // 2. Application Match
        let app_score = if a.bundle_id == b.bundle_id {
            1.0
        } else if a.app_name.to_lowercase() == b.app_name.to_lowercase() {
            0.8
        } else {
            0.0
        };

        // 3. Tag Overlap (Jaccard similarity)
        let tag_score = Self::jaccard_similarity(&a.tags, &b.tags);

        // 4. Key Indicator Overlap
        let indicator_score = Self::key_indicator_similarity(&a.key_indicators, &b.key_indicators);

        // Weighted combination
        CONTEXT_TYPE_WEIGHT * context_type_score
            + APP_WEIGHT * app_score
            + TAG_WEIGHT * tag_score
            + INDICATOR_WEIGHT * indicator_score
    }

    /// Calculate context type similarity
    fn context_type_similarity(a: &ContextType, b: &ContextType) -> f32 {
        if std::mem::discriminant(a) == std::mem::discriminant(b) {
            return 1.0;
        }

        // Same category
        let cat_a = Self::get_category_name(a);
        let cat_b = Self::get_category_name(b);
        if cat_a == cat_b {
            return 0.7;
        }

        // Related categories
        if Self::are_categories_related(&cat_a, &cat_b) {
            return 0.4;
        }

        0.0
    }

    /// Jaccard similarity between two sets
    fn jaccard_similarity(a: &HashSet<String>, b: &HashSet<String>) -> f32 {
        if a.is_empty() && b.is_empty() {
            return 1.0;
        }
        let intersection = a.intersection(b).count();
        let union = a.union(b).count();
        if union == 0 {
            1.0
        } else {
            intersection as f32 / union as f32
        }
    }

    /// Calculate similarity between key indicators
    fn key_indicator_similarity(a: &[String], b: &[String]) -> f32 {
        if a.is_empty() && b.is_empty() {
            return 1.0;
        }
        if a.is_empty() || b.is_empty() {
            return 0.0;
        }

        let a_set: HashSet<_> = a.iter().map(|s| s.to_lowercase()).collect();
        let b_set: HashSet<_> = b.iter().map(|s| s.to_lowercase()).collect();

        let intersection = a_set.intersection(&b_set).count();
        let union = a_set.union(&b_set).count();

        if union == 0 {
            1.0
        } else {
            intersection as f32 / union as f32
        }
    }

    /// Calculate recency score with exponential decay
    fn calculate_recency_score(&self, timestamp: DateTime<Utc>) -> f32 {
        let now = Utc::now();
        let age_secs = (now - timestamp).num_seconds().max(0) as f64;

        // Exponential decay: score = e^(-age / half_life * ln(2))
        let decay_rate = 0.693147 / self.recency_half_life; // ln(2) / half_life
        let score = (-decay_rate * age_secs).exp();

        score as f32
    }

    /// Calculate combined relevancy + recency score
    pub fn calculate_combined_score(
        &self,
        context: &ContextSummary,
        current: &ContextSummary,
    ) -> ScoredContext {
        let relevancy_score = Self::calculate_similarity(context, current);
        let recency_score = self.calculate_recency_score(context.timestamp);

        // Chain bonus: contexts in the same chain get a boost
        let is_same_chain = context.chain_id == current.chain_id;
        let chain_bonus = if is_same_chain { 0.1 } else { 0.0 };

        // Weighted combination: 60% relevancy, 40% recency
        const RELEVANCY_WEIGHT: f32 = 0.6;
        const RECENCY_WEIGHT: f32 = 0.4;

        let combined_score =
            (RELEVANCY_WEIGHT * relevancy_score + RECENCY_WEIGHT * recency_score + chain_bonus)
                .min(1.0);

        ScoredContext {
            summary: context.clone(),
            relevancy_score,
            recency_score,
            combined_score,
            is_same_chain,
        }
    }

    // ========================================================================
    // Context Summarization
    // ========================================================================

    /// Create a ContextSummary from RawContext
    pub fn summarize_context(&self, context: &RawContext, chain_id: String) -> ContextSummary {
        let tags = Self::extract_tags(context);
        let key_indicators = Self::extract_key_indicators(context);

        // Detect context type using bundle ID and window title
        let (context_type, confidence) = ContextType::from_app_bundle_id(&context.app_info.bundle_id);

        ContextSummary {
            id: Self::generate_context_id(),
            chain_id,
            app_name: context.app_info.name.clone(),
            bundle_id: context.app_info.bundle_id.clone(),
            window_title: context.app_info.window_title.clone(),
            context_type,
            context_confidence: confidence,
            timestamp: context.timestamp,
            tags,
            description: None, // Can be populated by LLM later
            activity_level: context.activity_metrics.activity_level.clone(),
            key_indicators,
            duration_secs: 0,
        }
    }

    /// Extract tags for similarity matching
    fn extract_tags(context: &RawContext) -> HashSet<String> {
        let mut tags = HashSet::new();

        // Add app name
        tags.insert(context.app_info.name.to_lowercase());

        // Add context type tags
        let (context_type, _) = ContextType::from_app_bundle_id(&context.app_info.bundle_id);
        for tag in context_type.to_embedding_tags() {
            tags.insert(tag.to_lowercase());
        }

        // Add browser-specific tags
        if context.app_info.is_browser {
            tags.insert("browser".to_string());
            if let Some(ref dom) = context.dom_data {
                if !dom.url.is_empty() {
                    if let Ok(parsed) = url::Url::parse(&dom.url) {
                        if let Some(domain) = parsed.domain() {
                            tags.insert(domain.to_lowercase());
                        }
                    }
                }
            }
        }

        // Add IDE-specific tags
        if context.app_info.is_ide {
            tags.insert("ide".to_string());
            tags.insert("coding".to_string());
            if let Some(ref file_path) = context.app_info.current_file_path {
                if let Some(ext) = std::path::Path::new(file_path)
                    .extension()
                    .and_then(|e| e.to_str())
                {
                    tags.insert(ext.to_lowercase());
                }
            }
        }

        tags
    }

    /// Extract key indicators from context
    fn extract_key_indicators(context: &RawContext) -> Vec<String> {
        let mut indicators = Vec::new();

        // URL from browser
        if let Some(ref dom) = context.dom_data {
            if !dom.url.is_empty() {
                indicators.push(dom.url.clone());
            }
            // Add page title if not empty
            if !dom.title.is_empty() {
                indicators.push(dom.title.clone());
            }
        }

        // File path from IDE
        if let Some(ref file_path) = context.app_info.current_file_path {
            indicators.push(file_path.clone());
        }
        if let Some(ref workspace) = context.app_info.workspace_path {
            indicators.push(workspace.clone());
        }

        // Window title
        if let Some(ref title) = context.app_info.window_title {
            indicators.push(title.clone());
        }

        indicators
    }

    // ========================================================================
    // Prompt Formatting
    // ========================================================================

    /// Format context chain for inclusion in tab completion prompts
    pub fn format_for_prompt(&self, chain: &ContextChainResult, max_chars: usize) -> String {
        let mut output = String::new();

        for scored in chain.contexts.iter().take(5) {
            let ctx = &scored.summary;
            let age = Self::format_age(ctx.timestamp);

            let line = format!(
                "- [{}] {}: {} ({})\n",
                age,
                ctx.app_name,
                ctx.window_title
                    .as_deref()
                    .unwrap_or("(no title)")
                    .chars()
                    .take(50)
                    .collect::<String>(),
                Self::get_category_name(&ctx.context_type)
            );

            if output.len() + line.len() > max_chars {
                break;
            }
            output.push_str(&line);
        }

        output
    }

    /// Get condensed context summary for CachedContext.screen_context
    pub async fn get_screen_context_string(&self, limit: usize) -> String {
        let summaries = self.summaries.read().await;
        let chain_id = self.current_chain_id.read().await.clone();

        let mut output = String::new();

        for ctx in summaries.iter().rev().take(limit) {
            let chain_marker = if ctx.chain_id == chain_id { "*" } else { " " };
            let line = format!(
                "{} {} | {} | {}\n",
                chain_marker,
                ctx.app_name,
                ctx.window_title.as_deref().unwrap_or("-"),
                Self::get_category_name(&ctx.context_type)
            );
            output.push_str(&line);
        }

        output
    }

    // ========================================================================
    // Statistics
    // ========================================================================

    /// Get memory statistics
    pub async fn get_stats(&self) -> ContextMemoryStats {
        let summaries = self.summaries.read().await;
        let chains = self.chains.read().await;
        let current_chain_id = self.current_chain_id.read().await.clone();

        let current_chain_length = summaries
            .iter()
            .filter(|ctx| ctx.chain_id == current_chain_id)
            .count();

        let oldest_age = summaries
            .front()
            .map(|ctx| (Utc::now() - ctx.timestamp).num_seconds().max(0) as u64)
            .unwrap_or(0);

        let avg_similarity = if summaries.len() >= 2 {
            let mut total = 0.0;
            let mut count = 0;
            let items: Vec<_> = summaries.iter().collect();
            for i in 1..items.len() {
                total += Self::calculate_similarity(items[i - 1], items[i]);
                count += 1;
            }
            if count > 0 {
                total / count as f32
            } else {
                0.0
            }
        } else {
            0.0
        };

        ContextMemoryStats {
            total_contexts: summaries.len(),
            total_chains: chains.len(),
            current_chain_length,
            oldest_context_age_secs: oldest_age,
            average_similarity: avg_similarity,
        }
    }

    /// Clear all memory
    pub async fn clear(&self) {
        self.summaries.write().await.clear();
        self.chains.write().await.clear();
        *self.current_chain_id.write().await = Self::generate_chain_id();
    }

    // ========================================================================
    // Private Helpers
    // ========================================================================

    fn generate_chain_id() -> String {
        format!("chain-{}", Uuid::new_v4().to_string()[..8].to_string())
    }

    fn generate_context_id() -> String {
        format!("ctx-{}", Uuid::new_v4().to_string()[..8].to_string())
    }

    fn get_category_name(context_type: &ContextType) -> &'static str {
        match context_type {
            ContextType::Development(_) => "Development",
            ContextType::Communication(_) => "Communication",
            ContextType::Research(_) => "Research",
            ContextType::Creative(_) => "Creative",
            ContextType::DataWork(_) => "DataWork",
            ContextType::Administration(_) => "Administration",
            ContextType::Multitasking(_) => "Multitasking",
            ContextType::Unknown => "Unknown",
        }
    }

    fn are_categories_related(a: &str, b: &str) -> bool {
        // Define related category pairs
        let related_pairs = [
            ("Development", "Research"),
            ("Research", "Development"),
            ("Development", "DataWork"),
            ("DataWork", "Development"),
            ("Communication", "Administration"),
            ("Administration", "Communication"),
            ("Creative", "Research"),
            ("Research", "Creative"),
        ];

        related_pairs.contains(&(a, b))
    }

    fn format_age(timestamp: DateTime<Utc>) -> String {
        let age_secs = (Utc::now() - timestamp).num_seconds().max(0);
        if age_secs < 60 {
            format!("{}s ago", age_secs)
        } else if age_secs < 3600 {
            format!("{}m ago", age_secs / 60)
        } else {
            format!("{}h ago", age_secs / 3600)
        }
    }

    fn calculate_chain_stats(
        &self,
        chain_id: &str,
        summaries: &VecDeque<ContextSummary>,
    ) -> ChainStats {
        let chain_contexts: Vec<_> = summaries
            .iter()
            .filter(|ctx| ctx.chain_id == chain_id)
            .collect();

        let chain_length = chain_contexts.len();

        let chain_duration = if chain_contexts.len() >= 2 {
            let first = chain_contexts.first().unwrap();
            let last = chain_contexts.last().unwrap();
            (last.timestamp - first.timestamp).num_seconds().max(0) as u64
        } else {
            0
        };

        // Find dominant context type
        let mut type_counts: HashMap<&str, usize> = HashMap::new();
        for ctx in &chain_contexts {
            let cat = Self::get_category_name(&ctx.context_type);
            *type_counts.entry(cat).or_insert(0) += 1;
        }
        let dominant_type = type_counts
            .into_iter()
            .max_by_key(|(_, count)| *count)
            .map(|(t, _)| t.to_string())
            .unwrap_or_else(|| "Unknown".to_string());

        // Count unique apps
        let app_diversity: HashSet<_> = chain_contexts.iter().map(|ctx| &ctx.app_name).collect();

        ChainStats {
            chain_length,
            chain_duration_secs: chain_duration,
            dominant_context_type: dominant_type,
            app_diversity: app_diversity.len(),
        }
    }
}

impl Default for ContextMemory {
    fn default() -> Self {
        Self::new()
    }
}

// ============================================================================
// Tests
// ============================================================================

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_jaccard_similarity() {
        let a: HashSet<String> = ["a", "b", "c"].iter().map(|s| s.to_string()).collect();
        let b: HashSet<String> = ["b", "c", "d"].iter().map(|s| s.to_string()).collect();

        let similarity = ContextMemory::jaccard_similarity(&a, &b);
        assert!((similarity - 0.5).abs() < 0.01); // 2 / 4 = 0.5
    }

    #[test]
    fn test_empty_jaccard() {
        let a: HashSet<String> = HashSet::new();
        let b: HashSet<String> = HashSet::new();
        assert_eq!(ContextMemory::jaccard_similarity(&a, &b), 1.0);
    }

    #[test]
    fn test_chain_id_generation() {
        let id1 = ContextMemory::generate_chain_id();
        let id2 = ContextMemory::generate_chain_id();
        assert_ne!(id1, id2);
        assert!(id1.starts_with("chain-"));
    }

    #[test]
    fn test_related_categories() {
        assert!(ContextMemory::are_categories_related(
            "Development",
            "Research"
        ));
        assert!(!ContextMemory::are_categories_related(
            "Development",
            "Communication"
        ));
    }
}
