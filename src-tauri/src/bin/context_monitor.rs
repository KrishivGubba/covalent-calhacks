use anyhow::Result;
use chrono::Utc;
use serde_json;
use std::time::Duration;
use tokio::time::interval;
use colored::*;

use src_tauri_lib::screen_context::{
    EnhancedContextCollector, ChromiumBridge, RegionAnalyzer, LLMAnalyzer,
    ContextAnalysisOutput, SystemReadiness, DOMData
};

#[tokio::main]
async fn main() -> Result<()> {
    println!("{}", "🔍 Covalent Context Monitor - Starting...".green().bold());
    println!("{}", "Press Ctrl+C to stop monitoring\n".yellow());
    
    // Initialize components
    let mut context_collector = EnhancedContextCollector::new()?;
    let mut chromium_bridge = ChromiumBridge::new();
    let mut region_analyzer = RegionAnalyzer::new();
    let mut llm_analyzer = LLMAnalyzer::new();
    
    // Initialize the collector
    context_collector.initialize().await?;
    
    println!("{}", "✅ All components initialized successfully".green());
    
    // Check system readiness
    let readiness = context_collector.check_system_readiness().await?;
    print_system_readiness(&readiness);
    
    // Set up monitoring interval (20 seconds)
    let mut interval = interval(Duration::from_secs(20));
    let mut iteration = 0;
    
    // Store previous states for change detection
    let mut previous_dom = None;
    let mut previous_screenshot = None;
    
    println!("\n{}", "🚀 Starting context monitoring (every 20 seconds)...".blue().bold());
    println!("{}", "=" .repeat(80).bright_black());
    
    loop {
        interval.tick().await;
        iteration += 1;
        
        println!("\n{}", format!("📊 Analysis #{} - {}", iteration, Utc::now().format("%H:%M:%S")).cyan().bold());
        println!("{}", "-".repeat(60).bright_black());
        
        match collect_and_analyze_context(
            &mut context_collector,
            &mut chromium_bridge,
            &mut region_analyzer,
            &mut llm_analyzer,
            &mut previous_dom,
            &mut previous_screenshot,
        ).await {
            Ok(analysis) => {
                print_analysis(&analysis, iteration);
            }
            Err(e) => {
                println!("{}", format!("❌ Error during analysis: {}", e).red());
            }
        }
        
        // Print separator
        println!("{}", "=".repeat(80).bright_black());
    }
}

async fn collect_and_analyze_context(
    context_collector: &mut EnhancedContextCollector,
    chromium_bridge: &mut ChromiumBridge,
    region_analyzer: &mut RegionAnalyzer,
    llm_analyzer: &mut LLMAnalyzer,
    previous_dom: &mut Option<DOMData>,
    _previous_screenshot: &mut Option<image::DynamicImage>,
) -> Result<ContextAnalysisOutput> {
    
    // 1. Collect raw context
    let raw_context = context_collector.collect_context().await?;
    
    // 2. Try to get DOM changes if browser is active
    let dom_changes = if raw_context.app_info.is_browser {
        match chromium_bridge.extract_browser_context().await {
            Ok(current_dom) => {
                let changes = chromium_bridge.detect_dom_changes(previous_dom.as_ref()).await.ok();
                *previous_dom = Some(current_dom);
                changes
            }
            Err(_) => {
                // Browser not available or no DevTools access
                None
            }
        }
    } else {
        None
    };
    
    // 3. Analyze screen region changes (simplified - would normally capture screenshot)
    let region_changes = if let Some(ref visual_data) = raw_context.visual_data {
        // Create a dummy screenshot for testing
        let dummy_screenshot = image::DynamicImage::new_rgb8(1920, 1080);
        
        match region_analyzer.analyze_screen_changes(&dummy_screenshot, Some(visual_data)) {
            Ok(changes) => Some(changes),
            Err(_) => None,
        }
    } else {
        None
    };
    
    // 4. Generate LLM analysis
    let analysis = llm_analyzer.analyze_context(
        &raw_context,
        dom_changes.as_ref(),
        region_changes.as_ref(),
    ).await?;
    
    Ok(analysis)
}

fn print_system_readiness(readiness: &SystemReadiness) {
    println!("\n{}", "🔧 System Readiness Check:".yellow().bold());
    
    let status = |available: bool| {
        if available { "✅".green() } else { "❌".red() }
    };
    
    println!("  {} Accessibility Permission: {}", 
        status(readiness.accessibility_permission), 
        if readiness.accessibility_permission { "Available" } else { "Not Available" }
    );
    
    println!("  {} Screen Recording Permission: {}", 
        status(readiness.screen_recording_permission), 
        if readiness.screen_recording_permission { "Available" } else { "Not Available" }
    );
    
    println!("  {} Browser Integration: {}", 
        status(readiness.browser_integration), 
        if readiness.browser_integration { "Available" } else { "Not Available" }
    );
    
    println!("  {} OCR Engine: {}", 
        status(readiness.ocr_engine), 
        if readiness.ocr_engine { "Available" } else { "Not Available" }
    );
    
    println!("  {} Overall Status: {}", 
        status(readiness.overall_ready), 
        if readiness.overall_ready { "Ready" } else { "Needs Setup" }
    );
    
    if !readiness.overall_ready {
        println!("\n{}", "⚠️  Some features may not work without proper permissions.".yellow());
        println!("{}", "   Enable Screen Recording and Accessibility in System Preferences.".yellow());
    }
}

fn print_analysis(analysis: &ContextAnalysisOutput, iteration: u32) {
    // App and Context Info
    println!("{} {}", "📱 App:".blue().bold(), analysis.app_name.white().bold());
    println!("{} {}", "🎯 Context:".blue().bold(), format!("{:?}", analysis.context_type).white());
    println!("{} {:.1}%", "🎲 Confidence:".blue().bold(), (analysis.confidence * 100.0).to_string().white());
    
    // Time Information
    let session_mins = analysis.session_duration_seconds / 60;
    let elapsed_secs = analysis.time_elapsed_seconds;
    println!("{} {}m {}s", "⏱️  Session:".blue().bold(), session_mins, analysis.session_duration_seconds % 60);
    
    if iteration > 1 {
        println!("{} {}s ago", "🔄 Last change:".blue().bold(), elapsed_secs);
    }
    
    // Activity and Workflow
    println!("{} {}", "⚡ Activity:".blue().bold(), analysis.activity_level.white());
    println!("{} {}", "🎬 Stage:".blue().bold(), analysis.workflow_stage.white());
    println!("{} {}", "🖱️  Pattern:".blue().bold(), analysis.interaction_pattern.white());
    
    // Description
    println!("\n{}", "📝 What's happening:".green().bold());
    println!("   {}", analysis.description.white());
    
    // Changes
    if analysis.changes_detected {
        println!("\n{}", "🔍 Recent Changes:".yellow().bold());
        for change in &analysis.key_changes {
            println!("   • {}", change.white());
        }
    } else {
        println!("\n{}", "😴 No significant changes detected".bright_black());
    }
    
    // Automation Opportunities
    if !analysis.automation_opportunities.is_empty() {
        println!("\n{}", "🤖 Automation Ideas:".magenta().bold());
        for opportunity in &analysis.automation_opportunities {
            println!("   💡 {}", opportunity.white());
        }
    }
    
    // Technical Details
    println!("\n{}", "🔧 Technical Details:".bright_black());
    println!("   Data Sources: {}", analysis.metadata.data_sources_used.join(", ").bright_black());
    println!("   Processing: {}ms", analysis.metadata.processing_time_ms.to_string().bright_black());
    println!("   Focus Areas: {}", analysis.metadata.focus_areas.join(", ").bright_black());
    
    if analysis.metadata.change_intensity > 0.0 {
        println!("   Change Intensity: {:.1}%", (analysis.metadata.change_intensity * 100.0).to_string().bright_black());
    }
    
    if analysis.metadata.context_switches > 0 {
        println!("   Context Switches: {}", analysis.metadata.context_switches.to_string().bright_black());
    }
    
    // JSON Output (for debugging)
    if std::env::var("COVALENT_DEBUG").is_ok() {
        println!("\n{}", "🐛 JSON Output:".bright_black());
        if let Ok(json) = serde_json::to_string_pretty(analysis) {
            println!("{}", json.bright_black());
        }
    }
}

// Add some utility functions for enhanced output
fn print_banner() {
    println!("{}", r#"
 ____                     _            _   
/ ___|_____   ____ _  ___| | ___ _ __ | |_ 
\___ \ _ \ \ / / _` |/ _ \ |/ _ \ '_ \| __|
 ___) | (_) \ V / (_| | __/ |  __/ | | | |_ 
|____/ \___/ \_/ \__,_|\___|_|\___|_| |_|\__|
                                           
    Context Monitoring Engine v0.1.0
"#.cyan().bold());
}

// Signal handler for graceful shutdown
async fn setup_signal_handler() -> Result<()> {
    #[cfg(unix)]
    {
        use tokio::signal;
        
        let mut sigterm = signal::unix::signal(signal::unix::SignalKind::terminate())?;
        let mut sigint = signal::unix::signal(signal::unix::SignalKind::interrupt())?;
        
        tokio::select! {
            _ = sigterm.recv() => {
                println!("\n{}", "📴 Received SIGTERM, shutting down gracefully...".yellow());
            }
            _ = sigint.recv() => {
                println!("\n{}", "📴 Received SIGINT (Ctrl+C), shutting down gracefully...".yellow());
            }
        }
    }
    
    #[cfg(not(unix))]
    {
        use tokio::signal;
        signal::ctrl_c().await?;
        println!("\n{}", "📴 Received Ctrl+C, shutting down gracefully...".yellow());
    }
    
    Ok(())
}