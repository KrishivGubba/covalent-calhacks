// Screen context module - Intelligent context detection and analysis

pub mod context_type;
pub mod context_data;
pub mod context_api;
pub mod context_loop;
//pub mod context_examples;
pub mod demo;
pub mod ocr_tesseract;
pub mod screen_capture;
//pub mod ocr_examples;

// macOS-specific integrations
pub mod macos_app_detector;
pub mod chromium_bridge;
pub mod safari_bridge;
pub mod accessibility_bridge;

// Smart collection and activity monitoring
pub mod smart_collector;
pub mod activity_monitor;
pub mod enhanced_context_collector;
pub mod region_analyzer;
pub mod llm_analyzer;

// Legacy modules (can be uncommented when ready to use)
// pub mod capture;
pub mod contextCollector;
// pub mod hybrid_llm;
// pub mod intent_analyzer;
// pub mod screenshot_region_detector;
// pub mod workflow_detector;

// Re-export main types for easier access
pub use context_data::*;
pub use context_type::{
    ContextType, DevelopmentType, CommunicationType, ResearchType, 
    CreativeType, DataWorkType, AdministrationType, IntentAnalysis, DeltaAnalysis
};
pub use context_api::{ContextApiClient, ContextPayload, ContextResponse};
pub use context_loop::ContextLoop;
pub use enhanced_context_collector::{EnhancedContextCollector, SystemReadiness};
pub use screen_capture::ScreenCapture;
pub use chromium_bridge::{ChromiumBridge, DOMChangeAnalysis};
pub use region_analyzer::{RegionAnalyzer, RegionChangeAnalysis};
pub use llm_analyzer::{LLMAnalyzer, ContextAnalysisOutput};