//! Quick CLI tool to visualize tab completion cache state
//! 
//! Run with: cargo run --bin cache_viz

use std::path::PathBuf;
use src_tauri_lib::tab_completion::MultiTierCache;

fn main() {
    println!("🔍 Tab Completion Cache Visualizer\n");
    
    // Find graph.db path
    let graph_db_path = find_graph_db();
    println!("📂 Using graph.db at: {}\n", graph_db_path);
    
    // Create cache instance
    let cache = MultiTierCache::new(graph_db_path);
    
    // Show visualization
    cache.visualize();
    
    // Also print JSON
    println!("\n📋 JSON State:");
    println!("{}", cache.get_state_json());
}

fn find_graph_db() -> String {
    // Try common locations
    let candidates = vec![
        PathBuf::from("../server/graph.db"),
        PathBuf::from("../../server/graph.db"),
        PathBuf::from("server/graph.db"),
        PathBuf::from("context-engine/graph.db"),
        PathBuf::from("../context-engine/graph.db"),
    ];
    
    for path in candidates {
        if path.exists() {
            return path.to_string_lossy().to_string();
        }
    }
    
    // Default fallback
    "../server/graph.db".to_string()
}

