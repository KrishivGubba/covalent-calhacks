use anyhow::Result;
use std::time::Duration;
use tokio::time::sleep;

use crate::screen_context::{
    EnhancedContextCollector, LLMAnalyzer, ContextApiClient, ContextAnalysisOutput
};

/// Synchronous context collection loop
/// Runs every 1-2 seconds, waiting for each iteration to complete before starting the next
pub struct ContextLoop {
    collector: EnhancedContextCollector,
    analyzer: LLMAnalyzer,
    api_client: ContextApiClient,
    interval: Duration,
    running: bool,
}

impl ContextLoop {
    /// Create a new context loop
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
        })
    }

    /// Set the collection interval (in seconds)
    pub fn set_interval(&mut self, seconds: u64) {
        self.interval = Duration::from_secs(seconds);
    }

    /// Initialize the collector
    pub async fn initialize(&self) -> Result<()> {
        self.collector.initialize().await
    }

    /// Start the synchronous collection loop
    /// This will run indefinitely until stopped
    pub async fn run(&mut self) -> Result<()> {
        self.running = true;
        println!("🚀 Starting synchronous context collection loop (interval: {:?})", self.interval);
        
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
        
        // Step 1: Collect context
        println!("  📊 Collecting context...");
        let raw_context = self.collector.collect_context().await?;
        
        // Step 2: Analyze with LLM (Claude)
        println!("  🤖 Analyzing with Claude...");
        let analysis = self.analyzer.analyze_context(&raw_context, None, None).await?;
        
        // Step 3: Send to Flask API
        println!("  📤 Sending to Flask API...");
        self.send_to_flask(&analysis).await?;
        
        println!("  ✓ App: {}", analysis.app_name);
        println!("  ✓ Description: {}", 
            if analysis.description.len() > 100 {
                format!("{}...", &analysis.description[..100])
            } else {
                analysis.description.clone()
            }
        );
        
        Ok(())
    }

    /// Send analysis to Flask API
    async fn send_to_flask(&self, analysis: &ContextAnalysisOutput) -> Result<()> {
        match self.api_client.send_analysis_output(analysis).await {
            Ok(response) => {
                println!("  ✓ Flask response: {} (UUID: {})", response.message, response.written);
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

