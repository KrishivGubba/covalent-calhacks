use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::time::{Duration, Instant};

use crate::screen_context::context_type::ContextType;
use crate::screen_context::ocr_tesseract::{OCRResult, ScreenRegion};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RawContext {
    pub app_info: AppInfo,
    pub dom_data: Option<DOMData>,
    pub ui_tree: Option<UITree>,
    pub ocr_data: Option<OCRData>,
    pub visual_data: Option<VisualData>,
    pub accessibility_data: Option<AccessibilityData>,
    pub file_context: Option<FileContext>,
    pub activity_metrics: ActivityMetrics,
    pub collection_metadata: CollectionMetadata,
    pub timestamp: DateTime<Utc>,
}

impl Default for RawContext {
    fn default() -> Self {
        Self {
            app_info: AppInfo::default(),
            dom_data: None,
            ui_tree: None,
            ocr_data: None,
            visual_data: None,
            accessibility_data: None,
            file_context: None,
            activity_metrics: ActivityMetrics::default(),
            collection_metadata: CollectionMetadata::default(),
            timestamp: Utc::now(),
        }
    }
}

impl RawContext {
    pub fn needs_ocr(&self) -> bool {
        // OCR needed if no DOM data and no accessibility data with meaningful content
        self.dom_data.is_none() && 
        (self.accessibility_data.is_none() || 
         self.accessibility_data.as_ref().map_or(true, |a| a.elements.len() < 5))
    }
    
    pub fn is_insufficient(&self) -> bool {
        // Context is insufficient if we have very little meaningful data
        let has_meaningful_dom = self.dom_data.as_ref()
            .map_or(false, |d| !d.visible_text.trim().is_empty());
        
        let has_meaningful_accessibility = self.accessibility_data.as_ref()
            .map_or(false, |a| !a.elements.is_empty());
        
        let has_meaningful_ocr = self.ocr_data.as_ref()
            .map_or(false, |o| o.results.iter().any(|r| !r.text.trim().is_empty()));
        
        !(has_meaningful_dom || has_meaningful_accessibility || has_meaningful_ocr)
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct AppInfo {
    pub name: String,
    pub bundle_id: String,
    pub version: Option<String>,
    pub window_title: Option<String>,
    pub window_id: Option<u32>,
    pub process_id: u32,
    pub executable_path: Option<String>,
    pub is_browser: bool,
    pub browser_type: Option<BrowserType>,
    pub is_ide: bool,
    pub ide_type: Option<IDEType>,
    pub current_file_path: Option<String>,
    pub workspace_path: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum BrowserType {
    Chrome,
    Safari,
    Firefox,
    Edge,
    Arc,
    Other(String),
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum IDEType {
    VSCode,
    Xcode,
    IntelliJ,
    PyCharm,
    WebStorm,
    Sublime,
    Atom,
    Vim,
    Emacs,
    Other(String),
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DOMData {
    pub url: String,
    pub title: String,
    pub active_element: Option<String>,
    pub forms: Vec<FormData>,
    pub visible_text: String,
    pub buttons: Vec<String>,
    pub inputs: Vec<InputData>,
    pub links: Vec<LinkData>,
    pub meta_data: HashMap<String, String>,
    pub scroll_position: Option<ScrollPosition>,
    pub viewport_size: Option<ViewportSize>,
    pub cookies: Option<Vec<String>>, // Domain names only for privacy
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FormData {
    pub action: String,
    pub method: String,
    pub fields: Vec<String>,
    pub has_file_upload: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct InputData {
    pub input_type: String,
    pub name: Option<String>,
    pub placeholder: Option<String>,
    pub value_length: usize, // Length only, not actual value for privacy
    pub is_focused: bool,
    pub is_required: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct LinkData {
    pub text: String,
    pub href: String,
    pub is_external: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct ScrollPosition {
    pub x: f64,
    pub y: f64,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct ViewportSize {
    pub width: u32,
    pub height: u32,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct UITree {
    pub root_element: UIElement,
    pub focused_element: Option<UIElementRef>,
    pub total_elements: usize,
    pub interactive_elements: Vec<UIElementRef>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct UIElement {
    pub element_type: String,
    pub title: Option<String>,
    pub value: Option<String>,
    pub description: Option<String>,
    pub role: Option<String>,
    pub bounds: Option<ElementBounds>,
    pub is_enabled: bool,
    pub is_visible: bool,
    pub is_focused: bool,
    pub children: Vec<UIElement>,
    pub attributes: HashMap<String, String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct UIElementRef {
    pub path: String, // XPath-like reference
    pub title: Option<String>,
    pub element_type: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ElementBounds {
    pub x: f64,
    pub y: f64,
    pub width: f64,
    pub height: f64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct OCRData {
    pub results: Vec<OCRResult>,
    pub total_confidence: f32,
    pub processing_time_ms: u64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct VisualData {
    pub screenshot_hash: String,
    pub changed_regions: Vec<ScreenRegion>,
    pub dominant_colors: Vec<Color>,
    pub text_regions: Vec<ScreenRegion>,
    pub ui_elements_detected: Vec<DetectedUIElement>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Color {
    pub r: u8,
    pub g: u8,
    pub b: u8,
    pub frequency: f32,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DetectedUIElement {
    pub element_type: String,
    pub bounds: ScreenRegion,
    pub confidence: f32,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AccessibilityData {
    pub elements: Vec<AccessibleElement>,
    pub focused_element: Option<String>,
    pub menu_structure: Option<MenuStructure>,
    pub window_info: WindowInfo,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AccessibleElement {
    pub ax_element_id: String,
    pub role: String,
    pub title: Option<String>,
    pub value: Option<String>,
    pub description: Option<String>,
    pub bounds: Option<ElementBounds>,
    pub is_enabled: bool,
    pub is_focused: bool,
    pub children_count: usize,
    pub parent_id: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MenuStructure {
    pub menu_items: Vec<MenuItem>,
    pub active_menu: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MenuItem {
    pub title: String,
    pub shortcut: Option<String>,
    pub is_enabled: bool,
    pub is_separator: bool,
    pub submenu: Option<Vec<MenuItem>>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct WindowInfo {
    pub title: String,
    pub bounds: ElementBounds,
    pub is_minimized: bool,
    pub is_main_window: bool,
    pub window_level: i32,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FileContext {
    pub current_file_path: Option<String>,
    pub file_type: Option<String>,
    pub file_size: Option<u64>,
    pub last_modified: Option<DateTime<Utc>>,
    pub project_root: Option<String>,
    pub git_info: Option<GitInfo>,
    pub recent_files: Vec<RecentFile>,
    pub open_tabs: Vec<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GitInfo {
    pub branch: String,
    pub commit_hash: String,
    pub has_uncommitted_changes: bool,
    pub remote_url: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RecentFile {
    pub path: String,
    pub last_accessed: DateTime<Utc>,
    pub file_type: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct ActivityMetrics {
    pub is_idle: bool,
    pub idle_duration: Option<Duration>,
    pub last_activity: DateTime<Utc>,
    pub activity_level: ActivityLevel,
    pub context_switches: u32,
    pub time_in_current_context: Duration,
    pub typing_activity: TypingActivity,
    pub mouse_activity: MouseActivity,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum ActivityLevel {
    Idle,
    Low,     // Occasional clicks/typing
    Medium,  // Regular interaction
    High,    // Very active typing/clicking
}

impl Default for ActivityLevel {
    fn default() -> Self {
        ActivityLevel::Medium
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct TypingActivity {
    pub keystrokes_per_minute: f32,
    pub last_keystroke: Option<DateTime<Utc>>,
    pub typing_patterns: TypingPatterns,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct TypingPatterns {
    pub burst_typing: bool,    // Fast bursts followed by pauses
    pub steady_typing: bool,   // Consistent rhythm
    pub hunt_and_peck: bool,   // Slow, irregular
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct MouseActivity {
    pub clicks_per_minute: f32,
    pub last_click: Option<DateTime<Utc>>,
    pub scroll_activity: ScrollActivity,
    pub movement_patterns: MousePatterns,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct ScrollActivity {
    pub scrolls_per_minute: f32,
    pub predominant_direction: ScrollDirection,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum ScrollDirection {
    Up,
    Down,
    Left,
    Right,
    Mixed,
}

impl Default for ScrollDirection {
    fn default() -> Self {
        ScrollDirection::Mixed
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct MousePatterns {
    pub precise_movements: bool,   // Small, precise movements (design work)
    pub broad_movements: bool,     // Large movements across screen
    pub hovering_behavior: bool,   // Lots of hovering over elements
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct CollectionMetadata {
    pub collection_duration_ms: u64,
    pub data_sources_attempted: Vec<DataSourceAttempt>,
    pub total_timeout_ms: u64,
    pub cache_hits: u32,
    pub cache_misses: u32,
    pub errors: Vec<CollectionError>,
    pub parallel_collections: u32,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DataSourceAttempt {
    pub source_type: DataSourceType,
    pub success: bool,
    pub duration_ms: u64,
    pub data_size_bytes: usize,
    pub from_cache: bool,
}

#[derive(Debug, Clone, Copy, Serialize, Deserialize, Hash, Eq, PartialEq)]
pub enum DataSourceType {
    AppInfo,
    DOM,
    Accessibility,
    OCR,
    Screenshot,
    FileSystem,
    ActivityMonitoring,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CollectionError {
    pub source: DataSourceType,
    pub error_type: String,
    pub message: String,
    pub occurred_at: DateTime<Utc>,
}

// System state for tracking changes between collections
#[derive(Debug, Clone)]
pub struct SystemState {
    pub screenshot: image::DynamicImage,
    pub screenshot_hash: String,
    pub app_info: AppInfo,
    pub context_type: ContextType,
    pub captured_at: Instant,
    pub activity_level: ActivityLevel,
}

// Activity timeline for context enrichment
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ActivityTimeline {
    pub entries: Vec<ActivityEntry>,
    pub current_session_start: DateTime<Utc>,
    pub total_active_time: Duration,
    pub context_switches_today: u32,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ActivityEntry {
    pub timestamp: DateTime<Utc>,
    pub context_type: ContextType,
    pub app_name: String,
    pub activity_level: ActivityLevel,
    pub duration: Duration,
    pub transition_type: TransitionType,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum TransitionType {
    AppSwitch,      // User switched to different app
    ContextSwitch,  // Same app, different context (e.g., different file in IDE)
    Return,         // Returned to previous context
    NewSession,     // Fresh start
}

// Collection priority queue item
#[derive(Debug, Clone)]
pub struct CollectionTask {
    pub task_type: DataSourceType,
    pub priority: u8,           // 0 = highest priority
    pub estimated_duration_ms: u64,
    pub depends_on: Vec<DataSourceType>,
    pub can_run_parallel: bool,
}

impl CollectionTask {
    pub fn new(
        task_type: DataSourceType,
        priority: u8,
        estimated_duration_ms: u64,
    ) -> Self {
        Self {
            task_type,
            priority,
            estimated_duration_ms,
            depends_on: Vec::new(),
            can_run_parallel: true,
        }
    }
    
    pub fn with_dependencies(mut self, deps: Vec<DataSourceType>) -> Self {
        self.depends_on = deps;
        self
    }
    
    pub fn sequential(mut self) -> Self {
        self.can_run_parallel = false;
        self
    }
}

impl Ord for CollectionTask {
    fn cmp(&self, other: &Self) -> std::cmp::Ordering {
        // Lower priority number = higher priority in queue
        other.priority.cmp(&self.priority)
    }
}

impl PartialOrd for CollectionTask {
    fn partial_cmp(&self, other: &Self) -> Option<std::cmp::Ordering> {
        Some(self.cmp(other))
    }
}

impl PartialEq for CollectionTask {
    fn eq(&self, other: &Self) -> bool {
        self.priority == other.priority
    }
}

impl Eq for CollectionTask {}