use anyhow::Result;
use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use std::sync::Arc;
use std::time::{Duration, SystemTime};

use crate::screen_context::chromium_bridge::DOMChangeAnalysis;
use crate::screen_context::context_data::RawContext;
use crate::screen_context::context_type::{ContextType, IntentAnalysis};
use crate::screen_context::region_analyzer::RegionChangeAnalysis;
use crate::screen_context::screen_capture::ScreenCapture;
use crate::ai_provider::{LLMProvider, ClaudeProvider};

/// LLM-powered context analyzer that generates structured output
pub struct LLMAnalyzer {
    session_start: SystemTime,
    last_analysis: Option<ContextAnalysisOutput>,
    llm_provider: Option<Arc<dyn LLMProvider>>,
    screen_capture: Arc<ScreenCapture>,
}

/// Final structured output for the frontend
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ContextAnalysisOutput {
    pub app_name: String,
    pub description: String, // Max 200 words
    pub context_type: ContextType,
    pub confidence: f32,
    pub time_elapsed_seconds: u64,
    pub session_duration_seconds: u64,
    pub activity_level: String,
    pub changes_detected: bool,
    pub key_changes: Vec<String>,
    pub workflow_stage: String,
    pub interaction_pattern: String,
    pub automation_opportunities: Vec<String>,
    pub timestamp: DateTime<Utc>,
    pub metadata: AnalysisMetadata,
    pub raw_ocr_text: Option<String>, // Raw OCR text for action generation
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AnalysisMetadata {
    pub data_sources_used: Vec<String>,
    pub processing_time_ms: u64,
    pub change_intensity: f32,
    pub focus_areas: Vec<String>,
    pub context_switches: u32,
}

impl LLMAnalyzer {
    pub fn new() -> Self {
        // Try to create fallback provider (will use Claude by default if available)
        let llm_provider = crate::ai_provider::create_default_provider().ok().map(Arc::from);
        
        let screen_capture = Arc::new(ScreenCapture::new().unwrap_or_else(|_| {
            // Create a default ScreenCapture if it fails
            panic!("Failed to create ScreenCapture");
        }));
        
        if llm_provider.is_none() {
            eprintln!("⚠️  Warning: No AI providers available. Set API keys in environment.");
        }
        
        Self {
            session_start: SystemTime::now(),
            last_analysis: None,
            llm_provider,
            screen_capture,
        }
    }
    
    /// Analyze context and generate structured output
    pub async fn analyze_context(
        &mut self,
        raw_context: &RawContext,
        dom_changes: Option<&DOMChangeAnalysis>,
        region_changes: Option<&RegionChangeAnalysis>,
    ) -> Result<ContextAnalysisOutput> {
        let start_time = std::time::Instant::now();
        
        // Calculate time metrics
        let session_duration = self.session_start.elapsed().unwrap_or(Duration::ZERO);
        let time_since_last = if let Some(ref last) = self.last_analysis {
            SystemTime::now()
                .duration_since(SystemTime::UNIX_EPOCH)
                .unwrap_or(Duration::ZERO)
                .as_secs()
                - last.timestamp.timestamp() as u64
        } else {
            0
        };
        
        // Detect context type from raw context
        let context_type = self.detect_context_type(raw_context);
        let confidence = context_type.confidence_score();
        
        // Generate description using Claude API or fallback to rule-based
        let description = self.generate_description_with_claude(
            raw_context, 
            &context_type, 
            dom_changes, 
            region_changes
        ).await.unwrap_or_else(|e| {
            eprintln!("⚠️  Claude description failed: {}, using fallback", e);
            self.generate_description_fallback(raw_context, &context_type, dom_changes, region_changes)
        });
        
        // Detect changes
        let (changes_detected, key_changes, change_intensity) = self.analyze_changes(dom_changes, region_changes);
        
        // Determine workflow stage
        let workflow_stage = self.determine_workflow_stage(raw_context, &context_type, &key_changes);
        
        // Analyze interaction patterns
        let interaction_pattern = self.analyze_interaction_pattern(raw_context, dom_changes);
        
        // Suggest automation opportunities
        let automation_opportunities = self.suggest_automation_opportunities(raw_context, &key_changes);
        
        // Determine focus areas
        let focus_areas = self.determine_focus_areas(raw_context, region_changes);
        
        // Get data sources used
        let data_sources_used = self.get_data_sources_used(raw_context);
        
        // Extract raw OCR text for action generation
        let raw_ocr_text = raw_context.ocr_data.as_ref().map(|ocr| {
            ocr.results.iter()
                .map(|r| r.text.as_str())
                .collect::<Vec<&str>>()
                .join("\n")
        });
        
        let output = ContextAnalysisOutput {
            app_name: raw_context.app_info.name.clone(),
            description,
            context_type,
            confidence,
            time_elapsed_seconds: time_since_last,
            session_duration_seconds: session_duration.as_secs(),
            activity_level: format!("{:?}", raw_context.activity_metrics.activity_level),
            changes_detected,
            key_changes,
            workflow_stage,
            interaction_pattern,
            automation_opportunities,
            timestamp: Utc::now(),
            metadata: AnalysisMetadata {
                data_sources_used,
                processing_time_ms: start_time.elapsed().as_millis() as u64,
                change_intensity,
                focus_areas,
                context_switches: raw_context.activity_metrics.context_switches,
            },
            raw_ocr_text,
        };
        
        self.last_analysis = Some(output.clone());
        Ok(output)
    }
    
    fn detect_context_type(&self, raw_context: &RawContext) -> ContextType {
        // Use bundle ID first
        let (context_from_bundle, confidence1) = ContextType::from_app_bundle_id(&raw_context.app_info.bundle_id);
        
        // Use window title if available
        let (context_from_title, confidence2) = if let Some(ref title) = raw_context.app_info.window_title {
            ContextType::from_window_title(title, Some(&raw_context.app_info.bundle_id))
        } else {
            (ContextType::Unknown, 0.0)
        };
        
        // Return the one with higher confidence
        if confidence2 > confidence1 {
            context_from_title
        } else {
            context_from_bundle
        }
    }
    
    /// Generate description using LLM provider with screenshot fallback
    async fn generate_description_with_claude(
        &self,
        raw_context: &RawContext,
        context_type: &ContextType,
        dom_changes: Option<&DOMChangeAnalysis>,
        region_changes: Option<&RegionChangeAnalysis>,
    ) -> Result<String> {
        let llm_provider = self.llm_provider.as_ref()
            .ok_or_else(|| anyhow::anyhow!("LLM provider not available"))?;
        
        // Build context metadata for Claude
        let metadata = self.build_metadata_for_claude(raw_context, context_type, dom_changes, region_changes);
        
        let system_prompt = "You are an AI assistant that analyzes user activity and context. \
            Generate a concise, natural description of what the user is currently doing. \
            Focus on the task, workflow stage, and key activities. Be specific but concise.
            (max 250 words)
            ";
        
        let user_prompt = format!(
            "Analyze this user context and generate a description:\n\n{}\n\n\
            Generate a concise description of what the user is doing.
            ",
            metadata
        );

        // Determine if we have sufficient context data to skip screenshot
        // Check for meaningful text content from DOM, accessibility, or OCR
        let has_meaningful_dom = raw_context.dom_data.as_ref()
            .map_or(false, |d| d.visible_text.trim().len() > 50);

        let has_meaningful_accessibility = raw_context.accessibility_data.as_ref()
            .map_or(false, |a| a.elements.len() >= 5);

        let has_meaningful_ocr = raw_context.ocr_data.as_ref()
            .map_or(false, |o| {
                let total_text_len: usize = o.results.iter().map(|r| r.text.len()).sum();
                total_text_len > 50 && o.total_confidence > 50.0
            });

        let has_sufficient_context = has_meaningful_dom || has_meaningful_accessibility || has_meaningful_ocr;

        if has_sufficient_context {
            // We have enough text context - use fast text-only LLM call
            eprintln!("📝 Using text-only LLM (sufficient context: DOM={}, Accessibility={}, OCR={})",
                has_meaningful_dom, has_meaningful_accessibility, has_meaningful_ocr);

            match llm_provider.generate(system_prompt, &user_prompt).await {
                Ok(description) => return Ok(description),
                Err(e) => {
                    // Fallback to screenshot if text-only fails
                    eprintln!("⚠️  Text-only LLM failed: {}, falling back to screenshot", e);
                }
            }
        } else {
            eprintln!("📸 Insufficient text context - using screenshot + vision LLM");
        }

        // Fallback: use screenshot for richer context when text data is insufficient
        self.generate_with_screenshot(llm_provider, &metadata).await
    }
    
    /// Generate description with screenshot using LLM vision
    async fn generate_with_screenshot(
        &self,
        llm_provider: &Arc<dyn LLMProvider>,
        metadata: &str,
    ) -> Result<String> {
        // Capture screenshot - with error handling to prevent crashes
        let screenshot = match self.screen_capture.capture_full_screen() {
            Ok(img) => img,
            Err(e) => {
                eprintln!("⚠️  Screenshot capture failed: {}, falling back to metadata-only analysis", e);
                return self.generate_fallback_description(metadata);
            }
        };
        
        // Convert to PNG bytes - with error handling
        let mut png_bytes = Vec::new();
        if let Err(e) = screenshot.write_to(&mut std::io::Cursor::new(&mut png_bytes), image::ImageFormat::Png) {
            eprintln!("⚠️  PNG encoding failed: {}, falling back to metadata-only analysis", e);
            return self.generate_fallback_description(metadata);
        }
        
        // Encode to base64
        let screenshot_base64 = ClaudeProvider::encode_image_to_base64(&png_bytes);
        
        let system_prompt = "You are an AI assistant that analyzes user activity and context. \
            Generate a concise, natural description of what the user is currently doing. \
            Focus on the task, workflow stage, and key activities. Be specific but concise.
            (max 250 words)";
        
        let user_prompt = format!(
            "Here is the user's screen. Analyze both the screenshot and this metadata:\n\n{}\n\n\
            Generate a concise yet detailed description of what the user is doing.",
            metadata
        );
        
        // Try vision API with fallback on failure (e.g., API credits exhausted, network issues)
        match llm_provider.generate_with_image(
            system_prompt,
            &user_prompt,
            &screenshot_base64
        ).await {
            Ok(description) => Ok(description),
            Err(e) => {
                eprintln!("⚠️  Vision API failed: {}, falling back to metadata-only analysis", e);
                self.generate_fallback_description(metadata)
            }
        }
    }
    
    /// Generate a simple fallback description from metadata when screenshot/vision fails
    fn generate_fallback_description(&self, metadata: &str) -> Result<String> {
        // Parse metadata to extract key information
        let lines: Vec<&str> = metadata.lines().collect();
        
        let mut app_name = "Unknown App";
        let mut context_type = "Unknown";
        let mut activity = "active";
        
        for line in lines {
            if line.starts_with("App: ") {
                app_name = line.strip_prefix("App: ").unwrap_or(app_name);
            } else if line.starts_with("Context Type: ") {
                context_type = line.strip_prefix("Context Type: ").unwrap_or(context_type);
            } else if line.contains("Idle") {
                activity = "idle";
            }
        }
        
        let description = format!(
            "User is working in {} ({}), currently {}. \
            Note: Visual analysis unavailable - using metadata only.",
            app_name, context_type, activity
        );
        
        eprintln!("📝 Generated fallback description: {}", description);
        Ok(description)
    }
    
    /// Build comprehensive metadata string for Claude
    fn build_metadata_for_claude(
        &self,
        raw_context: &RawContext,
        context_type: &ContextType,
        dom_changes: Option<&DOMChangeAnalysis>,
        region_changes: Option<&RegionChangeAnalysis>,
    ) -> String {
        let mut metadata = Vec::new();
        
        // App info
        metadata.push(format!("App: {}", raw_context.app_info.name));
        metadata.push(format!("Bundle ID: {}", raw_context.app_info.bundle_id));
        metadata.push(format!("Context Type: {}", context_type.category_name()));
        
        if let Some(ref title) = raw_context.app_info.window_title {
            metadata.push(format!("Window Title: {}", title));
        }
        
        if raw_context.app_info.is_browser {
            metadata.push("Browser: Yes".to_string());
        }
        
        if raw_context.app_info.is_ide {
            metadata.push("IDE: Yes".to_string());
            if let Some(ref file_path) = raw_context.app_info.current_file_path {
                metadata.push(format!("Current File: {}", file_path));
            }
        }
        
        // DOM data
        if let Some(dom_data) = &raw_context.dom_data {
            metadata.push(format!("URL: {}", dom_data.url));
            metadata.push(format!("Page Title: {}", dom_data.title));
            
            if !dom_data.visible_text.is_empty() {
                let truncated_text = if dom_data.visible_text.len() > 300 {
                    format!("{}...", &dom_data.visible_text[..300])
                } else {
                    dom_data.visible_text.clone()
                };
                metadata.push(format!("Visible Text: {}", truncated_text));
            }
            
            if !dom_data.forms.is_empty() {
                metadata.push(format!("Forms: {} present", dom_data.forms.len()));
            }
            
            if let Some(ref active_el) = dom_data.active_element {
                metadata.push(format!("Active Element: {}", active_el));
            }
        }

        // OCR data (screen text extraction)
        if let Some(ocr_data) = &raw_context.ocr_data {
            if !ocr_data.results.is_empty() {
                let ocr_text: String = ocr_data.results
                    .iter()
                    .map(|r| r.text.as_str())
                    .collect::<Vec<_>>()
                    .join(" ");
                let truncated_ocr = if ocr_text.len() > 500 {
                    format!("{}...", &ocr_text[..500])
                } else {
                    ocr_text
                };
                metadata.push(format!("Screen Text (OCR): {}", truncated_ocr));
                metadata.push(format!("OCR Confidence: {:.1}%", ocr_data.total_confidence));
            }
        }

        // Activity metrics
        metadata.push(format!("Activity Level: {:?}", raw_context.activity_metrics.activity_level));
        metadata.push(format!("Idle: {}", raw_context.activity_metrics.is_idle));
        
        // Changes
        if let Some(dom_changes) = dom_changes {
            if dom_changes.has_changes {
                let mut changes = Vec::new();
                if dom_changes.url_changed { changes.push("URL changed"); }
                if dom_changes.form_changes.input_focus_changed { changes.push("Input focus changed"); }
                if dom_changes.content_changes.scroll_changed { changes.push("Scrolled"); }
                if dom_changes.content_changes.text_similarity < 0.9 { changes.push("Text changed"); }
                metadata.push(format!("Recent Changes: {}", changes.join(", ")));
            }
        }
        
        if let Some(region_changes) = region_changes {
            if !region_changes.changed_regions.is_empty() {
                metadata.push(format!("Visual Changes: {:.1}% of screen", region_changes.total_change_percentage * 100.0));
            }
        }
        
        metadata.join("\n")
    }
    
    /// Fallback description generation (rule-based)
    fn generate_description_fallback(
        &self,
        raw_context: &RawContext,
        context_type: &ContextType,
        dom_changes: Option<&DOMChangeAnalysis>,
        region_changes: Option<&RegionChangeAnalysis>,
    ) -> String {
        let mut description_parts = Vec::new();
        
        // Start with app and context
        description_parts.push(format!(
            "User is working in {} ({})",
            raw_context.app_info.name,
            context_type.category_name()
        ));
        
        // Add window title context if available
        if let Some(ref title) = raw_context.app_info.window_title {
            if !title.trim().is_empty() && title != &raw_context.app_info.name {
                description_parts.push(format!("focusing on: {}", title));
            }
        }
        
        // Add DOM context if available
        if let Some(dom_data) = &raw_context.dom_data {
            if !dom_data.url.is_empty() && dom_data.url != "about:blank" {
                description_parts.push(format!("browsing: {}", dom_data.title));
                
                if !dom_data.forms.is_empty() {
                    description_parts.push(format!("interacting with {} forms", dom_data.forms.len()));
                }
                
                if dom_data.inputs.iter().any(|input| input.is_focused) {
                    description_parts.push("currently typing in an input field".to_string());
                }
            }
        }
        
        // Add change information
        if let Some(dom_changes) = dom_changes {
            if dom_changes.has_changes {
                let mut change_descriptions = Vec::new();
                
                if dom_changes.url_changed {
                    change_descriptions.push("navigated to new page");
                }
                
                if dom_changes.form_changes.input_focus_changed {
                    change_descriptions.push("changed input focus");
                }
                
                if dom_changes.content_changes.scroll_changed {
                    change_descriptions.push("scrolled page");
                }
                
                if !change_descriptions.is_empty() {
                    description_parts.push(format!("recently: {}", change_descriptions.join(", ")));
                }
            }
        }
        
        // Add region change information
        if let Some(region_changes) = region_changes {
            if region_changes.total_change_percentage > 10.0 {
                description_parts.push(format!(
                    "significant visual changes detected ({:.1}% of screen)",
                    region_changes.total_change_percentage
                ));
            }
        }
        
        // Add activity level
        match raw_context.activity_metrics.activity_level {
            crate::screen_context::context_data::ActivityLevel::High => {
                description_parts.push("very active with frequent interactions".to_string());
            }
            crate::screen_context::context_data::ActivityLevel::Medium => {
                description_parts.push("moderate activity level".to_string());
            }
            crate::screen_context::context_data::ActivityLevel::Low => {
                description_parts.push("light activity, possibly reading or thinking".to_string());
            }
            crate::screen_context::context_data::ActivityLevel::Idle => {
                description_parts.push("currently idle".to_string());
            }
        }
        
        // Join and limit to 200 words
        let full_description = description_parts.join(". ");
        self.limit_to_words(&full_description, 200)
    }
    
    fn analyze_changes(
        &self,
        dom_changes: Option<&DOMChangeAnalysis>,
        region_changes: Option<&RegionChangeAnalysis>,
    ) -> (bool, Vec<String>, f32) {
        let mut changes_detected = false;
        let mut key_changes = Vec::new();
        let mut max_intensity = 0.0f32;
        
        if let Some(dom_changes) = dom_changes {
            if dom_changes.has_changes {
                changes_detected = true;
                
                if dom_changes.url_changed {
                    key_changes.push("Page navigation".to_string());
                    max_intensity = max_intensity.max(0.8);
                }
                
                if dom_changes.form_changes.new_input_values > 0 {
                    key_changes.push(format!("Form input changes ({})", dom_changes.form_changes.new_input_values));
                    max_intensity = max_intensity.max(0.6);
                }
                
                if dom_changes.content_changes.scroll_changed {
                    key_changes.push("Page scrolling".to_string());
                    max_intensity = max_intensity.max(0.3);
                }
                
                if dom_changes.content_changes.text_similarity < 0.8 {
                    key_changes.push("Significant content changes".to_string());
                    max_intensity = max_intensity.max(0.7);
                }
            }
        }
        
        if let Some(region_changes) = region_changes {
            if !region_changes.changed_regions.is_empty() {
                changes_detected = true;
                
                for changed_region in &region_changes.changed_regions {
                    let change_desc = format!("{:?} in screen region", changed_region.change_type);
                    key_changes.push(change_desc);
                    max_intensity = max_intensity.max(changed_region.change_intensity);
                }
            }
            
            if region_changes.total_change_percentage > 20.0 {
                key_changes.push("Major visual interface changes".to_string());
                max_intensity = max_intensity.max(0.9);
            }
        }
        
        (changes_detected, key_changes, max_intensity)
    }
    
    fn determine_workflow_stage(
        &self,
        raw_context: &RawContext,
        context_type: &ContextType,
        key_changes: &[String],
    ) -> String {
        match context_type {
            ContextType::Development(_) => {
                if let Some(ref title) = raw_context.app_info.window_title {
                    if title.contains("debug") || title.contains("Debug") {
                        return "Debugging".to_string();
                    }
                    if title.contains("test") || title.contains("Test") {
                        return "Testing".to_string();
                    }
                    if title.contains(".md") || title.contains("README") {
                        return "Documentation".to_string();
                    }
                }
                
                if raw_context.activity_metrics.typing_activity.keystrokes_per_minute > 60.0 {
                    "Active Coding".to_string()
                } else {
                    "Code Review/Reading".to_string()
                }
            }
            ContextType::Communication(_) => {
                if key_changes.iter().any(|c| c.contains("input")) {
                    "Composing Message".to_string()
                } else {
                    "Reading/Listening".to_string()
                }
            }
            ContextType::Research(_) => {
                if key_changes.iter().any(|c| c.contains("navigation")) {
                    "Information Gathering".to_string()
                } else {
                    "Deep Reading".to_string()
                }
            }
            ContextType::Creative(_) => {
                if raw_context.activity_metrics.mouse_activity.clicks_per_minute > 30.0 {
                    "Active Design Work".to_string()
                } else {
                    "Planning/Reviewing".to_string()
                }
            }
            _ => "Working".to_string(),
        }
    }
    
    fn analyze_interaction_pattern(
        &self,
        raw_context: &RawContext,
        dom_changes: Option<&DOMChangeAnalysis>,
    ) -> String {
        let typing = &raw_context.activity_metrics.typing_activity;
        let mouse = &raw_context.activity_metrics.mouse_activity;
        
        if typing.keystrokes_per_minute > 80.0 {
            if typing.typing_patterns.burst_typing {
                "Intensive typing with bursts".to_string()
            } else {
                "Steady fast typing".to_string()
            }
        } else if mouse.clicks_per_minute > 40.0 {
            "Mouse-heavy interaction".to_string()
        } else if let Some(dom_changes) = dom_changes {
            if dom_changes.content_changes.scroll_changed {
                "Scrolling and reading".to_string()
            } else {
                "Passive observation".to_string()
            }
        } else {
            "Mixed interaction".to_string()
        }
    }
    
    fn suggest_automation_opportunities(&self, raw_context: &RawContext, key_changes: &[String]) -> Vec<String> {
        let mut opportunities = Vec::new();
        
        // Form-based automation
        if let Some(dom_data) = &raw_context.dom_data {
            if dom_data.forms.len() > 1 {
                opportunities.push("Multiple forms detected - consider form auto-fill".to_string());
            }
            
            if dom_data.inputs.iter().filter(|i| i.is_required).count() > 3 {
                opportunities.push("Many required fields - template or macro could help".to_string());
            }
        }
        
        // Repetitive navigation
        if key_changes.iter().filter(|c| c.contains("navigation")).count() > 3 {
            opportunities.push("Frequent navigation - bookmark or shortcut recommended".to_string());
        }
        
        // High typing activity
        if raw_context.activity_metrics.typing_activity.keystrokes_per_minute > 100.0 {
            opportunities.push("High typing volume - text expansion or snippets could help".to_string());
        }
        
        // Context switching
        if raw_context.activity_metrics.context_switches > 5 {
            opportunities.push("Frequent app switching - workspace organization might help".to_string());
        }
        
        opportunities
    }
    
    fn determine_focus_areas(&self, raw_context: &RawContext, region_changes: Option<&RegionChangeAnalysis>) -> Vec<String> {
        let mut focus_areas = Vec::new();
        
        // Add app-based focus
        focus_areas.push(raw_context.app_info.name.clone());
        
        // Add region-based focus if available
        if let Some(region_changes) = region_changes {
            if let Some(ref most_active) = region_changes.most_active_region {
                focus_areas.push(format!("Screen region: {}", most_active));
            }
        }
        
        // Add DOM-based focus
        if let Some(dom_data) = &raw_context.dom_data {
            if let Some(ref active_element) = dom_data.active_element {
                focus_areas.push(format!("DOM element: {}", active_element));
            }
        }
        
        focus_areas
    }
    
    fn get_data_sources_used(&self, raw_context: &RawContext) -> Vec<String> {
        let mut sources = vec!["App Detection".to_string()];
        
        if raw_context.dom_data.is_some() {
            sources.push("DOM Analysis".to_string());
        }
        
        if raw_context.accessibility_data.is_some() {
            sources.push("Accessibility".to_string());
        }
        
        if raw_context.ocr_data.is_some() {
            sources.push("OCR".to_string());
        }
        
        if raw_context.visual_data.is_some() {
            sources.push("Visual Analysis".to_string());
        }
        
        sources.push("Activity Monitoring".to_string());
        
        sources
    }
    
    fn limit_to_words(&self, text: &str, max_words: usize) -> String {
        let words: Vec<&str> = text.split_whitespace().collect();
        if words.len() <= max_words {
            text.to_string()
        } else {
            words[..max_words].join(" ") + "..."
        }
    }
    
    /// Get the current session statistics
    pub fn get_session_stats(&self) -> SessionStats {
        SessionStats {
            session_duration: self.session_start.elapsed().unwrap_or(Duration::ZERO),
            total_analyses: if self.last_analysis.is_some() { 1 } else { 0 },
            last_analysis_time: self.last_analysis.as_ref().map(|a| a.timestamp),
        }
    }
    
    /// Reset the session
    pub fn reset_session(&mut self) {
        self.session_start = SystemTime::now();
        self.last_analysis = None;
    }
}

#[derive(Debug, Clone)]
pub struct SessionStats {
    pub session_duration: Duration,
    pub total_analyses: u32,
    pub last_analysis_time: Option<DateTime<Utc>>,
}

impl Default for LLMAnalyzer {
    fn default() -> Self {
        Self::new()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::screen_context::context_data::*;
    
    #[tokio::test]
    async fn test_llm_analyzer_creation() {
        let analyzer = LLMAnalyzer::new();
        let stats = analyzer.get_session_stats();
        assert_eq!(stats.total_analyses, 0);
    }
    
    #[test]
    fn test_word_limiting() {
        let analyzer = LLMAnalyzer::new();
        let long_text = "one two three four five six seven eight nine ten";
        let limited = analyzer.limit_to_words(long_text, 5);
        assert_eq!(limited, "one two three four five...");
        
        let short_text = "one two three";
        let not_limited = analyzer.limit_to_words(short_text, 5);
        assert_eq!(not_limited, "one two three");
    }
    
    #[tokio::test]
    async fn test_context_analysis() {
        let mut analyzer = LLMAnalyzer::new();
        
        let raw_context = RawContext {
            app_info: AppInfo {
                name: "Test App".to_string(),
                bundle_id: "com.test.app".to_string(),
                window_title: Some("Test Window".to_string()),
                ..Default::default()
            },
            ..Default::default()
        };
        
        let result = analyzer.analyze_context(&raw_context, None, None).await;
        assert!(result.is_ok());
        
        let output = result.unwrap();
        assert_eq!(output.app_name, "Test App");
        assert!(!output.description.is_empty());
    }
}