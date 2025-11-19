pub mod model;
pub mod cache;
pub mod trigger;
pub mod adapters;
pub mod injector;
pub mod prompt_builder;

pub use model::ModelInvoker;
pub use cache::{MultiTierCache, CachedContext, CacheResult, ActivityType, Pattern};
pub use trigger::{CompletionTrigger, CompletionSuggestion};
pub use adapters::{ContextExtractor, BrowserAdapter, TerminalAdapter, NativeTextAdapter};
pub use injector::inject_completion_text;
pub use prompt_builder::build_prompt;

use std::sync::Arc;
use anyhow::Result;

/// Initialize the tab completion system
pub fn initialize(graph_db_path: String) -> Result<Arc<CompletionTrigger>> {
    println!("🚀 Initializing Universal Tab Completion System...");
    
    // Create multi-tier cache
    let cache = Arc::new(MultiTierCache::new(graph_db_path));
    
    // Create completion trigger
    let trigger = Arc::new(CompletionTrigger::new(cache)?);
    
    println!("✅ Tab completion system initialized");
    
    Ok(trigger)
}

