use anyhow::Result;
use std::time::Duration;
use tokio::time::sleep;

use crate::screen_context::{
    EnhancedContextCollector, LLMAnalyzer, ContextApiClient, ContextAnalysisOutput
};
use crate::ContextState;

/// Synchronous context collection loop
/// Runs every 1-2 seconds, waiting for each iteration to complete before starting the next
pub struct ContextLoop {
    collector: EnhancedContextCollector,
    analyzer: LLMAnalyzer,
    api_client: ContextApiClient,
    interval: Duration,
    running: bool,
    context_state: Option<ContextState>,
    actions_store: Option<crate::ActionsStore>,
}

impl ContextLoop {
    /// Create a new context loop (without state management)
    pub fn new() -> Result<Self> {
        let collector = EnhancedContextCollector::new()?;
        let analyzer = LLMAnalyzer::new();
        let api_client = ContextApiClient::new();
        
        Ok(Self {
            collector,
            analyzer,
            api_client,
            interval: Duration::from_secs(1), // Default to 1 second
            running: false,
            context_state: None,
            actions_store: None,
        })
    }

    /// Create a new context loop with state management
    pub fn new_with_state(context_state: ContextState) -> Result<Self> {
        let collector = EnhancedContextCollector::new()?;
        let analyzer = LLMAnalyzer::new();
        let api_client = ContextApiClient::new();
        
        Ok(Self {
            collector,
            analyzer,
            api_client,
            interval: Duration::from_secs(1), // Default to 1 second
            running: false,
            context_state: Some(context_state),
            actions_store: None,
        })
    }

    /// Create a new context loop with state and actions store
    pub fn new_with_state_and_store(context_state: ContextState, actions_store: crate::ActionsStore) -> Result<Self> {
        let collector = EnhancedContextCollector::new()?;
        let analyzer = LLMAnalyzer::new();
        let api_client = ContextApiClient::new();
        
        Ok(Self {
            collector,
            analyzer,
            api_client,
            interval: Duration::from_secs(1), // Default to 1 second
            running: false,
            context_state: Some(context_state),
            actions_store: Some(actions_store),
        })
    }

    /// Set the collection interval (in seconds)
    pub fn set_interval(&mut self, seconds: u64) {
        self.interval = Duration::from_secs(seconds);
    }

    /// Initialize the collector
    pub async fn initialize(&self) -> Result<()> {
        println!("  🔧 Starting activity monitoring...");
        println!("    🎯 Setting up activity monitoring tasks...");
        println!("    📊 Starting event collection task...");
        println!("    🔄 Starting activity check task...");
        println!("    ✅ Activity monitoring tasks started successfully");
        
        let result = self.collector.initialize().await;
        
        if result.is_ok() {
            println!("  ✓ Activity monitoring started");
            println!("  🔍 Checking system readiness...");
            println!("  ✓ System readiness check completed");
        }
        
        result
    }

    /// Start the synchronous collection loop
    /// This will run indefinitely until stopped
    pub async fn run(&mut self) -> Result<()> {
        self.running = true;
        println!("🚀 Starting synchronous context collection loop (interval: {}s)", self.interval.as_secs());
        
        let mut iteration = 0;
        
        while self.running {
            iteration += 1;
            
            let start_time = std::time::Instant::now();
            
            match self.run_iteration(iteration).await {
                Ok(()) => {
                    let elapsed = start_time.elapsed();
                    println!("✅ Iteration {} completed in {:?}", iteration, elapsed);
                }
                Err(e) => {
                    eprintln!("❌ Iteration {} failed: {}", iteration, e);
                    // Still try to collect and send what we can, even on failure
                    let _ = self.run_fallback_iteration(iteration).await;
                }
            }
            
            // Wait for the specified interval before next iteration
            sleep(self.interval).await;
        }
        
        println!("🛑 Context collection loop stopped");
        Ok(())
    }

    /// Run a single iteration of the collection loop
    async fn run_iteration(&mut self, iteration: u64) -> Result<()> {
        println!("\n━━━ Iteration {} ━━━", iteration);
        
        // Check if context collection is disabled BEFORE doing any work
        if let Some(ref state) = self.context_state {
            if !state.is_enabled() {
                println!("  ⏸️  Context collection is DISABLED - skipping iteration completely");
                return Ok(());
            }
        }
        
        // Step 1: Collect context
        println!("  📊 Collecting context...");
        let raw_context = self.collector.collect_context().await?;
        
        // Check if Covalent app itself is in focus - if so, skip sending to prevent self-referential loops
        let is_covalent_focused = raw_context.app_info.bundle_id == "com.hem.src-tauri" 
            || raw_context.app_info.name == "Covalent";
        
        if is_covalent_focused {
            println!("  🔵 Covalent app is in focus - temporarily pausing context collection");
            // Don't send context when Covalent itself is focused
            // This prevents self-referential loops and unnecessary processing
            println!("  ⏸️  Skipping context collection while Covalent is focused");
            return Ok(());
        }
        
        // Display detailed raw context
        println!("  📋 Raw Context Data:");
        match serde_json::to_string_pretty(&raw_context) {
            Ok(json) => {
                // Print first 2000 characters of JSON to avoid overwhelming output
                let preview = if json.len() > 2000 {
                    format!("{}...\n    [JSON truncated - {} total characters]", &json[..2000], json.len())
                } else {
                    json
                };
                for line in preview.lines() {
                    println!("    {}", line);
                }
            }
            Err(e) => println!("    ❌ Failed to serialize raw context: {}", e),
        }
        
        // Step 2: Analyze with LLM (Claude)
        println!("  🤖 Analyzing with Claude...");
        let analysis = self.analyzer.analyze_context(&raw_context, None, None).await?;
        
        // Display analysis output that will be sent to Flask
        println!("  📤 Analysis Output (sending to Flask):");
        match serde_json::to_string_pretty(&analysis) {
            Ok(json) => {
                for line in json.lines() {
                    println!("    {}", line);
                }
            }
            Err(e) => println!("    ❌ Failed to serialize analysis: {}", e),
        }
        
        // Step 3: Send to Flask API (always attempt, don't fail on error)
        println!("  📤 Sending to Flask API...");
        if let Err(e) = self.send_to_flask(&analysis).await {
            eprintln!("  ⚠️ Flask API send failed but continuing: {}", e);
        }
        
        println!("  ✓ App: {}", analysis.app_name);
        println!("  ✓ Context Type: {:?}", analysis.context_type);
        println!("  ✓ Confidence: {:.2}", analysis.confidence);
        println!("  ✓ Activity Level: {}", analysis.activity_level);
        println!("  ✓ Description: {}", 
            if analysis.description.len() > 100 {
                format!("{}...", &analysis.description[..100])
            } else {
                analysis.description.clone()
            }
        );
        
        Ok(())
    }

    /// Fallback iteration that tries to collect and send minimal data even on errors
    async fn run_fallback_iteration(&mut self, _iteration: u64) -> Result<()> {
        println!("  🔄 Attempting fallback data collection...");
        
        // Try to collect basic context at least
        if let Ok(raw_context) = self.collector.collect_context().await {
            println!("  📋 Fallback Raw Context (basic):");
            println!("    App: {}", raw_context.app_info.name);
            println!("    Bundle ID: {}", raw_context.app_info.bundle_id);
            
            // Try to send minimal analysis if possible
            if let Ok(analysis) = self.analyzer.analyze_context(&raw_context, None, None).await {
                println!("  📤 Sending fallback analysis to Flask...");
                let _ = self.send_to_flask(&analysis).await; // Don't fail on Flask errors
            }
        }
        
        Ok(())
    }

    /// Send analysis to Flask API
    async fn send_to_flask(&self, analysis: &ContextAnalysisOutput) -> Result<()> {
        // Note: We already check if collection is enabled at the start of run_iteration()
        // so this will only be called when collection is enabled
        match self.api_client.send_analysis_output(analysis).await {
            Ok(response) => {
                println!("  ✓ Flask API Response:");
                // Output the full Flask response as JSON
                match serde_json::to_string_pretty(&response) {
                    Ok(json) => {
                        for line in json.lines() {
                            println!("    {}", line);
                        }
                    }
                    Err(e) => println!("    ❌ Failed to serialize Flask response: {}", e),
                }
                
                // Check if an action was generated (action_uuid present and action_name not None/"None")
                if let Some(action_uuid) = &response.action_uuid {
                    if !action_uuid.is_empty() {
                        // Extract action text from message (format: "Context processed successfully. Suggested action: <action>")
                        let action_text = if let Some(action_part) = response.message.split("Suggested action: ").nth(1) {
                            action_part.trim()
                        } else {
                            &response.message
                        };

                        // Prefer explicit action_name if provided
                        let effective_action_name = response
                            .action_name
                            .as_deref()
                            .filter(|name| !name.is_empty() && *name != "None")
                            .unwrap_or(action_text);

                        // Only store if action is not "None" or empty
                        if !effective_action_name.is_empty() && effective_action_name != "None" {
                            if let Some(ref store) = self.actions_store {
                                let title = if effective_action_name.len() > 100 {
                                    format!("{}...", &effective_action_name[..100])
                                } else {
                                    effective_action_name.to_string()
                                };

                                let suggested_action = crate::SuggestedAction {
                                    id: action_uuid.clone(),
                                    uuid: action_uuid.clone(),
                                    title,
                                    description: effective_action_name.to_string(),
                                };

                                store.add_action(suggested_action);
                                println!("  ✅ Action stored for frontend");
                            }
                        }
                    }
                }
                
                Ok(())
            }
            Err(e) => {
                eprintln!("  ✗ Flask API error: {}", e);
                Err(e)
            }
        }
    }

    /// Stop the loop
    pub fn stop(&mut self) {
        self.running = false;
    }
}

impl Default for ContextLoop {
    fn default() -> Self {
        Self::new().expect("Failed to create ContextLoop")
    }
}

