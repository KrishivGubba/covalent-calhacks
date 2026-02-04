pub mod model;
pub mod cache;
pub mod trigger;
pub mod adapters;
pub mod injector;
pub mod prompt_builder;
pub mod api_client;
pub mod graph_db;
pub mod terminal_display;
pub mod hotkey;
pub mod cursor_position;
pub mod window_manager;
pub mod decline;

#[cfg(target_os = "macos")]
pub mod macos_keyboard;

#[cfg(test)]
mod tab_completion_test;

pub use model::ModelInvoker;
pub use cache::{MultiTierCache, CachedContext, CacheResult, ActivityType, Pattern};
pub use trigger::{CompletionTrigger, CompletionSuggestion};
pub use adapters::{ContextExtractor, BrowserAdapter, TerminalAdapter, NativeTextAdapter, CodeAdapter};
pub use injector::inject_completion_text;
pub use prompt_builder::build_prompt;
pub use api_client::{TabCompletionApiClient, PredictionRequest, PredictionResponse, DeclineFeedbackRequest};
pub use graph_db::{GraphDatabase, NodeData, DataEntry};
pub use hotkey::{HotkeyHandler, DismissInfo};
pub use cursor_position::{CursorPosition, get_cursor_position_with_fallback};
pub use window_manager::CompletionWindowManager;
pub use decline::{DeclineContext, ActionSummary, EnrichedPredictionContext};

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

