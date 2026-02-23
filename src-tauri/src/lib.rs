// Module declarations
pub mod ai_provider;
pub mod screen_context;
pub mod tab_completion;
use tauri::menu::{Menu, MenuItem, PredefinedMenuItem, Submenu};
use tauri::{Manager, Emitter};
use std::process::{Child, Command};
use std::sync::{Arc, Mutex, RwLock, atomic::{AtomicBool, Ordering}};
use std::path::PathBuf;

/// Find the overlap between the end of the buffer and the start of the prediction.
/// Returns the number of characters that overlap.
/// Example: buffer="git ad", prediction="add ." -> overlap is 2 ("ad")
fn find_overlap(buffer: &str, prediction: &str) -> usize {
    let buffer_chars: Vec<char> = buffer.chars().collect();
    let pred_chars: Vec<char> = prediction.chars().collect();

    // Find longest suffix of buffer that is prefix of prediction
    for start in 0..buffer_chars.len() {
        let suffix: Vec<char> = buffer_chars[start..].to_vec();
        if pred_chars.len() >= suffix.len() && pred_chars[..suffix.len()] == suffix[..] {
            return suffix.len();
        }
    }
    0
}

// Suggested action from Flask
#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
pub struct SuggestedAction {
    pub id: String,
    pub uuid: String,
    pub title: String,           // action_name from Flask
    pub description: String,     // action_plan from Flask (contains full context for execution)
}

// Context collection state - controls whether context is being collected and sent
#[derive(Clone)]
pub struct ContextState {
    // Controls whether context collection is active
    // Set to false to pause context collection (e.g., when actions are running, app is in focus, or user toggles)
    pub is_enabled: Arc<AtomicBool>,
    // Tracks if user manually paused (vs automatic pause for action execution)
    // When true, we should NOT auto-resume after actions complete
    pub user_paused: Arc<AtomicBool>,
    // List of app names/bundle IDs excluded from context collection
    pub excluded_apps: Arc<RwLock<Vec<String>>>,
}

// Store for suggested actions
#[derive(Clone)]
pub struct ActionsStore {
    actions: Arc<Mutex<Vec<SuggestedAction>>>,
}

impl ActionsStore {
    fn new() -> Self {
        Self {
            actions: Arc::new(Mutex::new(Vec::new())),
        }
    }

    pub fn add_action(&self, action: SuggestedAction) {
        if let Ok(mut actions) = self.actions.lock() {
            // Add new action to the beginning of the list
            actions.insert(0, action);
            // Keep only the last 20 actions
            if actions.len() > 20 {
                actions.truncate(20);
            }
            println!("📝 Added action to store. Total actions: {}", actions.len());
        }
    }

    pub fn get_actions(&self) -> Vec<SuggestedAction> {
        self.actions.lock().unwrap_or_else(|e| e.into_inner()).clone()
    }

    pub fn clear_actions(&self) {
        if let Ok(mut actions) = self.actions.lock() {
            actions.clear();
            println!("🗑️  Cleared all actions from store");
        }
    }

    pub fn update_action(&self, action_uuid: &str, title: String, description: String) {
        if let Ok(mut actions) = self.actions.lock() {
            if let Some(action) = actions.iter_mut().find(|a| a.uuid == action_uuid) {
                action.title = title;
                action.description = description;
                println!("✏️  Updated action in store: {}", action_uuid);
            }
        }
    }
}

impl ContextState {
    fn new() -> Self {
        Self {
            is_enabled: Arc::new(AtomicBool::new(true)), // Enabled by default
            user_paused: Arc::new(AtomicBool::new(false)), // Not manually paused by default
            excluded_apps: Arc::new(RwLock::new(Vec::new())),
        }
    }

    pub fn get_excluded_apps(&self) -> Vec<String> {
        self.excluded_apps.read().unwrap_or_else(|e| e.into_inner()).clone()
    }

    pub fn set_excluded_apps_list(&self, apps: Vec<String>) {
        if let Ok(mut list) = self.excluded_apps.write() {
            *list = apps;
        }
    }

    /// Returns true if the given app name or bundle ID is in the excluded list (case-insensitive).
    pub fn is_app_excluded(&self, name: &str, bundle_id: &str) -> bool {
        let list = self.excluded_apps.read().unwrap_or_else(|e| e.into_inner());
        let name_lower = name.to_lowercase();
        let bundle_lower = bundle_id.to_lowercase();
        list.iter().any(|entry| {
            let entry_lower = entry.to_lowercase();
            entry_lower == name_lower || entry_lower == bundle_lower
        })
    }

    pub fn is_enabled(&self) -> bool {
        self.is_enabled.load(Ordering::Relaxed)
    }

    pub fn is_user_paused(&self) -> bool {
        self.user_paused.load(Ordering::Relaxed)
    }

    pub fn enable(&self) {
        println!("🟢 Context collection ENABLED");
        self.is_enabled.store(true, Ordering::Relaxed);
    }

    pub fn disable(&self) {
        println!("🔴 Context collection DISABLED");
        self.is_enabled.store(false, Ordering::Relaxed);
    }
    
    // Enable only if user hasn't manually paused
    pub fn enable_if_not_user_paused(&self) {
        if !self.user_paused.load(Ordering::Relaxed) {
            println!("🟢 Context collection ENABLED (auto-resume)");
            self.is_enabled.store(true, Ordering::Relaxed);
        } else {
            println!("⏸️  Context collection remains PAUSED (user manually paused)");
        }
    }

    pub fn toggle(&self) -> bool {
        let new_state = !self.is_enabled();
        self.is_enabled.store(new_state, Ordering::Relaxed);
        if new_state {
            println!("🟢 Context collection ENABLED (toggled)");
        } else {
            println!("🔴 Context collection DISABLED (toggled)");
        }
        new_state
    }
}

fn resolve_server_binary(app_dir: &PathBuf, server_name: &str, is_dev: bool) -> PathBuf {
    if is_dev {
        app_dir.join("dist-servers").join(server_name).join(server_name)
    } else {
        app_dir.join("servers").join(server_name).join(server_name)
    }
}

fn ensure_executable(path: &PathBuf) {
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        if let Ok(metadata) = std::fs::metadata(path) {
            let mut perms = metadata.permissions();
            perms.set_mode(0o755);
            let _ = std::fs::set_permissions(path, perms);
        }
    }
}

/// Kill any process currently listening on the given port.
fn kill_process_on_port(port: u16) {
    #[cfg(unix)]
    {
        let output = Command::new("lsof")
            .args(["-ti", &format!(":{}", port)])
            .output();
        if let Ok(output) = output {
            let pids = String::from_utf8_lossy(&output.stdout);
            for pid_str in pids.split_whitespace() {
                if let Ok(pid) = pid_str.trim().parse::<i32>() {
                    println!("⚠️  Killing stale process on port {} (PID: {})", port, pid);
                    let _ = Command::new("kill").arg(pid.to_string()).output();
                }
            }
            if !pids.is_empty() {
                std::thread::sleep(std::time::Duration::from_millis(500));
            }
        }
    }
}

/// Poll a URL until it responds with the expected status or we time out.
/// If `accept_any` is true, any HTTP response (even 4xx/5xx) counts as "alive".
fn wait_for_server(url: &str, timeout_secs: u64, accept_any: bool) -> bool {
    let start = std::time::Instant::now();
    let timeout = std::time::Duration::from_secs(timeout_secs);
    let poll_interval = std::time::Duration::from_millis(500);

    while start.elapsed() < timeout {
        if let Ok(output) = Command::new("curl")
            .args(["-s", "-o", "/dev/null", "-w", "%{http_code}", url])
            .output()
        {
            let status = String::from_utf8_lossy(&output.stdout).trim().to_string();
            if accept_any && status != "000" {
                return true;
            }
            if !accept_any && status == "200" {
                return true;
            }
        }
        std::thread::sleep(poll_interval);
    }
    false
}

struct FlaskServer {
    process: Arc<Mutex<Option<Child>>>,
}

impl FlaskServer {
    fn new() -> Self {
        Self {
            process: Arc::new(Mutex::new(None)),
        }
    }

    fn start(&self, app_dir: PathBuf, is_dev: bool, data_dir: Option<&PathBuf>) -> Result<(), String> {
        let binary = resolve_server_binary(&app_dir, "flask-server", is_dev);

        if !binary.exists() {
            return Err(format!("Flask server binary not found at {:?}", binary));
        }

        kill_process_on_port(5001);
        ensure_executable(&binary);

        let work_dir = binary.parent().unwrap().to_path_buf();
        println!("Starting Flask server binary: {:?}", binary);

        let mut cmd = Command::new(&binary);
        cmd.current_dir(&work_dir)
            .stdout(std::process::Stdio::inherit())
            .stderr(std::process::Stdio::inherit());

        if let Ok(env_path) = std::fs::read_to_string(app_dir.join(".env")) {
            for line in env_path.lines() {
                let line = line.trim();
                if line.is_empty() || line.starts_with('#') {
                    continue;
                }
                if let Some((key, value)) = line.split_once('=') {
                    cmd.env(key.trim(), value.trim());
                }
            }
        }

        if let Some(dir) = data_dir {
            let db_path = dir.join("graph.db");
            cmd.env("GRAPH_DB_PATH", db_path.to_string_lossy().as_ref());
            cmd.env("COVALENT_DATA_DIR", dir.to_string_lossy().as_ref());
        }

        match cmd.spawn() {
            Ok(child) => {
                println!("Flask server started with PID: {:?}", child.id());
                *self.process.lock().unwrap() = Some(child);

                if wait_for_server("http://127.0.0.1:5001/health", 30, false) {
                    println!("✅ Flask server is healthy and serving on port 5001");
                } else {
                    eprintln!("⚠️  Flask server started but health check timed out after 30s");
                }
                Ok(())
            }
            Err(e) => {
                eprintln!("Failed to start Flask server: {}", e);
                Err(format!("Failed to start Flask server: {}", e))
            }
        }
    }

    fn stop(&self) {
        if let Ok(mut process_guard) = self.process.lock() {
            if let Some(mut child) = process_guard.take() {
                println!("Stopping Flask server (PID: {:?})", child.id());
                let _ = child.kill();
                let _ = child.wait();
            }
        }
    }
}

impl Drop for FlaskServer {
    fn drop(&mut self) {
        self.stop();
    }
}

struct McpServer {
    process: Arc<Mutex<Option<Child>>>,
}

impl McpServer {
    fn new() -> Self {
        Self {
            process: Arc::new(Mutex::new(None)),
        }
    }

    fn start(&self, app_dir: PathBuf, is_dev: bool, data_dir: Option<&PathBuf>) -> Result<(), String> {
        let binary = resolve_server_binary(&app_dir, "mcp-server", is_dev);

        if !binary.exists() {
            return Err(format!("MCP server binary not found at {:?}", binary));
        }

        kill_process_on_port(8001);
        ensure_executable(&binary);

        let work_dir = binary.parent().unwrap().to_path_buf();
        println!("Starting MCP server binary: {:?}", binary);

        let mut cmd = Command::new(&binary);
        cmd.current_dir(&work_dir)
            .stdout(std::process::Stdio::inherit())
            .stderr(std::process::Stdio::inherit());

        if let Ok(env_path) = std::fs::read_to_string(app_dir.join(".env")) {
            for line in env_path.lines() {
                let line = line.trim();
                if line.is_empty() || line.starts_with('#') {
                    continue;
                }
                if let Some((key, value)) = line.split_once('=') {
                    cmd.env(key.trim(), value.trim());
                }
            }
        }

        if let Some(dir) = data_dir {
            let db_path = dir.join("graph.db");
            cmd.env("GRAPH_DB_PATH", db_path.to_string_lossy().as_ref());
            cmd.env("COVALENT_DATA_DIR", dir.to_string_lossy().as_ref());
        }

        match cmd.spawn() {
            Ok(child) => {
                println!("MCP server started with PID: {:?}", child.id());
                *self.process.lock().unwrap() = Some(child);

                let mcp_port = std::env::var("MCP_PORT").unwrap_or_else(|_| "8001".to_string());
                let mcp_url = format!("http://127.0.0.1:{}/mcp", mcp_port);
                if wait_for_server(&mcp_url, 15, true) {
                    println!("✅ MCP server is healthy and serving on port {}", mcp_port);
                } else {
                    eprintln!("⚠️  MCP server started but health check timed out after 15s");
                }
                Ok(())
            }
            Err(e) => {
                eprintln!("Failed to start MCP server: {}", e);
                Err(format!("Failed to start MCP server: {}", e))
            }
        }
    }

    fn stop(&self) {
        if let Ok(mut process_guard) = self.process.lock() {
            if let Some(mut child) = process_guard.take() {
                println!("Stopping MCP server (PID: {:?})", child.id());
                let _ = child.kill();
                let _ = child.wait();
            }
        }
    }
}

impl Drop for McpServer {
    fn drop(&mut self) {
        self.stop();
    }
}

// Ollama server state management
struct OllamaServer {
    process: Arc<Mutex<Option<Child>>>,
    was_already_running: Arc<Mutex<bool>>,
}

impl OllamaServer {
    fn new() -> Self {
        Self {
            process: Arc::new(Mutex::new(None)),
            was_already_running: Arc::new(Mutex::new(false)),
        }
    }

    fn start(&self) -> Result<(), String> {
        // Check if ollama is already running by trying to connect
        let already_running = std::process::Command::new("curl")
            .args(["-s", "-o", "/dev/null", "-w", "%{http_code}", "http://localhost:11434/api/tags"])
            .output()
            .map(|o| String::from_utf8_lossy(&o.stdout).trim() == "200")
            .unwrap_or(false);

        if already_running {
            println!("✓ Ollama is already running (not managed by Covalent)");
            *self.was_already_running.lock().unwrap() = true;
            return Ok(());
        }

        // Start ollama serve
        match Command::new("ollama")
            .arg("serve")
            .stdout(std::process::Stdio::null())
            .stderr(std::process::Stdio::null())
            .spawn()
        {
            Ok(child) => {
                println!("✓ Ollama serve started with PID: {:?}", child.id());
                *self.process.lock().unwrap() = Some(child);
                // Give it a moment to initialize
                std::thread::sleep(std::time::Duration::from_secs(2));
                Ok(())
            }
            Err(e) => {
                eprintln!("⚠️  Failed to start Ollama: {}", e);
                eprintln!("   Make sure Ollama is installed: https://ollama.ai");
                Err(format!("Failed to start Ollama: {}", e))
            }
        }
    }

    fn stop(&self) {
        // Only stop if we started it (don't kill user's existing ollama)
        if *self.was_already_running.lock().unwrap() {
            println!("🦙 Ollama was already running - leaving it alone");
            return;
        }

        if let Ok(mut process_guard) = self.process.lock() {
            if let Some(mut child) = process_guard.take() {
                println!("🦙 Stopping Ollama server (PID: {:?})", child.id());
                let _ = child.kill();
                let _ = child.wait();
                println!("✓ Ollama server stopped");
            }
        }
    }
}

impl Drop for OllamaServer {
    fn drop(&mut self) {
        self.stop();
    }
}

// Learn more about Tauri commands at https://tauri.app/develop/calling-rust/
#[tauri::command]
fn greet(name: &str) -> String {
    format!("eat shit {}", name)
}

#[tauri::command]
fn toggle_profile() {
    println!("Profile toggled");
    // TODO: Implement profile functionality
}

#[tauri::command]
fn toggle_link_mcps() {
    println!("Link MCPs toggled");
    // TODO: Implement MCP linking functionality
}

// Context collection control commands
#[tauri::command]
fn toggle_context_collection(state: tauri::State<ContextState>) -> bool {
    state.toggle()
}

#[tauri::command]
fn enable_context_collection(state: tauri::State<ContextState>) {
    // Clear user_paused flag when user explicitly resumes
    state.user_paused.store(false, Ordering::Relaxed);
    state.enable();
}

#[tauri::command]
fn disable_context_collection(state: tauri::State<ContextState>) {
    // Set user_paused flag when user explicitly pauses
    state.user_paused.store(true, Ordering::Relaxed);
    state.disable();
}

#[tauri::command]
fn get_context_collection_status(state: tauri::State<ContextState>) -> bool {
    state.is_enabled()
}

#[tauri::command]
fn enable_context_collection_if_not_user_paused(state: tauri::State<ContextState>) {
    state.enable_if_not_user_paused();
}

// --- Settings persistence helpers ---

/// Returns the path to the shared settings JSON file, creating parent dirs if needed.
fn settings_file_path(app: &tauri::AppHandle) -> Option<std::path::PathBuf> {
    use tauri::Manager;
    let dir = app.path().app_data_dir().ok()?;
    std::fs::create_dir_all(&dir).ok()?;
    Some(dir.join("settings.json"))
}

/// Load the persisted settings JSON, returning a mutable Value (empty object on any error).
fn load_settings(app: &tauri::AppHandle) -> serde_json::Value {
    let path = match settings_file_path(app) {
        Some(p) => p,
        None => return serde_json::json!({}),
    };
    std::fs::read_to_string(&path)
        .ok()
        .and_then(|s| serde_json::from_str(&s).ok())
        .unwrap_or_else(|| serde_json::json!({}))
}

/// Persist a single key/value pair in the settings JSON file.
fn save_setting(app: &tauri::AppHandle, key: &str, value: serde_json::Value) {
    let path = match settings_file_path(app) {
        Some(p) => p,
        None => {
            eprintln!("⚠️  Could not resolve settings file path");
            return;
        }
    };
    let mut settings = load_settings(app);
    settings[key] = value;
    match serde_json::to_string_pretty(&settings) {
        Ok(json) => {
            if let Err(e) = std::fs::write(&path, json) {
                eprintln!("⚠️  Failed to write settings file: {}", e);
            }
        }
        Err(e) => eprintln!("⚠️  Failed to serialize settings: {}", e),
    }
}

// Tab completion control commands
#[tauri::command]
fn get_tab_completion_status(trigger: tauri::State<std::sync::Arc<tab_completion::CompletionTrigger>>) -> bool {
    trigger.is_tab_completion_enabled()
}

#[tauri::command]
fn set_tab_completion_enabled(
    app: tauri::AppHandle,
    trigger: tauri::State<std::sync::Arc<tab_completion::CompletionTrigger>>,
    enabled: bool,
) {
    trigger.set_tab_completion_enabled(enabled);
    save_setting(&app, "tab_completion_enabled", serde_json::Value::Bool(enabled));
}

#[tauri::command]
fn toggle_tab_completion(
    app: tauri::AppHandle,
    trigger: tauri::State<std::sync::Arc<tab_completion::CompletionTrigger>>,
) -> bool {
    let new_state = trigger.toggle_tab_completion();
    save_setting(&app, "tab_completion_enabled", serde_json::Value::Bool(new_state));
    new_state
}

// Plan action command - Phase 1 of new action flow
// Returns action plan for user approval/editing before execution
#[tauri::command]
async fn plan_action(
    action_uuid: String,
    action_override: Option<serde_json::Value>,
    state: tauri::State<'_, ContextState>
) -> Result<serde_json::Value, String> {
    use screen_context::ContextApiClient;
    
    println!("📋 Planning action: {}", action_uuid);
    
    // Disable context collection during planning
    state.disable();
    
    let api_client = ContextApiClient::new();
    
    let result = api_client
        .plan_action(action_uuid, action_override)
        .await
        .map_err(|e| format!("Failed to plan action: {}", e));
    
    match &result {
        Ok(response) => {
            println!("✅ Action plan response:");
            println!("{}", serde_json::to_string_pretty(response).unwrap_or_else(|_| format!("{:?}", response)));
        }
        Err(e) => {
            println!("❌ Action planning failed: {}", e);
            // Re-enable on error only if user hasn't manually paused
            state.enable_if_not_user_paused();
        }
    }
    
    // Keep context collection disabled until action is executed or cancelled
    // Frontend will call enable_context_collection when done
    
    result
}

// Execute action command - Phase 2 of new action flow
// Called after user approves/edits the action plan
// Supports both single-action (legacy) and multi-action (new) formats
#[tauri::command]
async fn execute_action(
    action_uuid: String,
    // Legacy single-action parameters (optional)
    tool_name: Option<String>,
    parameters: Option<serde_json::Value>,
    // New multi-action parameters (optional)
    actions: Option<Vec<serde_json::Value>>,
    state: tauri::State<'_, ContextState>
) -> Result<serde_json::Value, String> {
    use screen_context::ContextApiClient;
    
    let api_client = ContextApiClient::new();
    
    let result = if let Some(actions_array) = actions {
        // Multi-action execution
        println!("🚀 Executing {} action(s) for: {}", actions_array.len(), action_uuid);
        
        api_client
            .execute_action_chain(action_uuid, actions_array)
            .await
            .map_err(|e| format!("Failed to execute action chain: {}", e))
    } else if let (Some(tool), Some(params)) = (tool_name, parameters) {
        // Legacy single-action execution
        println!("🚀 Executing single action: {} with tool {}", action_uuid, tool);
        
        api_client
            .execute_action(action_uuid, tool, params)
            .await
            .map_err(|e| format!("Failed to execute action: {}", e))
    } else {
        return Err("Either 'actions' array or 'tool_name' + 'parameters' must be provided".to_string());
    };
    
    match &result {
        Ok(response) => {
            println!("✅ Action execution response:");
            println!("{}", serde_json::to_string_pretty(response).unwrap_or_else(|_| format!("{:?}", response)));
        }
        Err(e) => {
            println!("❌ Action execution failed: {}", e);
        }
    }
    
    // Re-enable context collection after action completes, but only if user hasn't manually paused
    tokio::time::sleep(tokio::time::Duration::from_secs(2)).await;
    state.enable_if_not_user_paused();
    
    result
}

// Edit action command (optional persistence)
#[tauri::command]
async fn edit_action(
    action_uuid: String,
    action_name: String,
    action_plan: String,
    persist: bool,
    store: tauri::State<'_, ActionsStore>
) -> Result<serde_json::Value, String> {
    use screen_context::ContextApiClient;

    println!("✏️  Editing action: {} (persist: {})", action_uuid, persist);

    let api_client = ContextApiClient::new();
    let result = api_client
        .edit_action(action_uuid.clone(), action_name.clone(), action_plan.clone(), persist)
        .await
        .map_err(|e| format!("Failed to edit action: {}", e));

    if persist {
        store.update_action(&action_uuid, action_name, action_plan);
    }

    result
}

// Get suggested actions
#[tauri::command]
fn get_suggested_actions(store: tauri::State<ActionsStore>) -> Vec<SuggestedAction> {
    store.get_actions()
}

// Clear all actions
#[tauri::command]
fn clear_suggested_actions(store: tauri::State<ActionsStore>) {
    store.clear_actions();
}

// Get cache state visualization (for observability)
#[tauri::command]
fn get_cache_state(trigger: tauri::State<std::sync::Arc<tab_completion::CompletionTrigger>>) -> String {
    // Print to terminal
    trigger.visualize_cache();
    // Return JSON for frontend
    trigger.get_cache_state_json()
}

// Get cursor position for ghost text overlay
#[tauri::command]
fn get_cursor_position() -> Result<(i32, i32), String> {
    #[cfg(target_os = "macos")]
    {
        use core_graphics::display::CGDisplay;
        use core_graphics::event::CGEvent;
        use core_graphics::event_source::{CGEventSource, CGEventSourceStateID};
        
        // Get mouse location (best approximation for cursor position)
        if let Ok(source) = CGEventSource::new(CGEventSourceStateID::CombinedSessionState) {
            if let Ok(event) = CGEvent::new(source) {
                let location = event.location();
                return Ok((location.x as i32, location.y as i32));
            }
        }
        
        // Fallback to display center
        let main_display = CGDisplay::main();
        let bounds = main_display.bounds();
        Ok((bounds.size.width as i32 / 2, bounds.size.height as i32 / 2))
    }
    
    #[cfg(not(target_os = "macos"))]
    {
        Err("Cursor position only supported on macOS".to_string())
    }
}

// Dashboard commands

#[derive(Debug, serde::Serialize, serde::Deserialize)]
pub struct ActionHistoryItem {
    pub action_uuid: String,
    pub action_type: String,
    pub action_data: String,
    pub creation_timestamp: String,
    pub node_uuid: String,
}

#[tauri::command]
fn get_actions_history() -> Result<Vec<ActionHistoryItem>, String> {
    // TODO: Read from actual database
    // For now, return placeholder data
    println!("📊 Fetching actions history");
    Ok(vec![])
}

#[derive(Debug, serde::Serialize, serde::Deserialize)]
pub struct MemoryGraphData {
    pub nodes: Vec<GraphNode>,
    pub edges: Vec<GraphEdge>,
}

#[derive(Debug, serde::Serialize, serde::Deserialize)]
pub struct GraphNode {
    pub id: String,
    pub label: String,
    pub metadata: String,
}

#[derive(Debug, serde::Serialize, serde::Deserialize)]
pub struct GraphEdge {
    pub from: String,
    pub to: String,
}

#[tauri::command]
fn get_memory_graph_data() -> Result<MemoryGraphData, String> {
    // TODO: Read from graph.db and format for visualization
    println!("🧠 Fetching memory graph data");
    Ok(MemoryGraphData {
        nodes: vec![],
        edges: vec![],
    })
}

#[tauri::command]
fn get_excluded_apps(
    app: tauri::AppHandle,
    state: tauri::State<ContextState>,
) -> Result<Vec<String>, String> {
    let settings = load_settings(&app);
    if let Some(arr) = settings.get("excluded_apps").and_then(|v| v.as_array()) {
        let apps: Vec<String> = arr
            .iter()
            .filter_map(|v| v.as_str().map(|s| s.to_string()))
            .collect();
        // Keep ContextState in sync
        state.set_excluded_apps_list(apps.clone());
        println!("🔒 Loaded {} excluded apps from settings", apps.len());
        Ok(apps)
    } else {
        // No excluded apps saved yet — return empty list
        Ok(vec![])
    }
}

#[tauri::command]
fn set_excluded_apps(
    app: tauri::AppHandle,
    state: tauri::State<ContextState>,
    apps: Vec<String>,
) -> Result<(), String> {
    // Persist to settings.json
    let json_arr: serde_json::Value = serde_json::Value::Array(
        apps.iter().map(|s| serde_json::Value::String(s.clone())).collect(),
    );
    save_setting(&app, "excluded_apps", json_arr);
    // Update live state so context loop sees change immediately
    state.set_excluded_apps_list(apps.clone());
    println!("🔒 Saved {} excluded apps", apps.len());
    Ok(())
}

#[tauri::command]
async fn get_auth_status() -> Result<serde_json::Value, String> {
    println!("🔐 Checking auth status");

    let flask_base_url = std::env::var("FLASK_BASE_URL")
        .unwrap_or_else(|_| "http://localhost:5001".to_string());

    match crate::ai_provider::auth::fetch_current_session(&flask_base_url).await {
        Some(session) => Ok(serde_json::json!({
            "authenticated": true,
            "user": session.user_info,
            "user_id": session.user_id,
            "expired": session.expired,
        })),
        None => Ok(serde_json::json!({
            "authenticated": false,
            "user": null,
            "user_id": null,
        })),
    }
}

// Open dashboard and navigate to history page
#[tauri::command]
fn open_dashboard_history(app: tauri::AppHandle) -> Result<(), String> {
    println!("🎛️  Opening dashboard to history page");
    if let Some(window) = app.get_webview_window("dashboard") {
        window.show().map_err(|e| e.to_string())?;
        window.set_focus().map_err(|e| e.to_string())?;
        // Emit event to navigate to history
        app.emit_to("dashboard", "navigate-to-history", ()).map_err(|e| e.to_string())?;
        Ok(())
    } else {
        Err("Dashboard window not found".to_string())
    }
}

// Open main window (FloatingAssistant)
#[tauri::command]
fn open_main_window(app: tauri::AppHandle) -> Result<(), String> {
    println!("🪟 Opening main window");
    if let Some(window) = app.get_webview_window("main") {
        window.show().map_err(|e| e.to_string())?;
        window.set_focus().map_err(|e| e.to_string())?;
        Ok(())
    } else {
        Err("Main window not found".to_string())
    }
}

// Check if any Covalent window is currently focused
#[tauri::command]
fn is_covalent_focused(app: tauri::AppHandle) -> Result<bool, String> {
    // Check all Covalent windows to see if any are focused
    let window_labels = vec!["main", "dashboard", "ghost-text", "completion-popup"];
    
    for label in window_labels {
        if let Some(window) = app.get_webview_window(label) {
            // Check if window is visible and focused
            if let Ok(is_focused) = window.is_focused() {
                if is_focused {
                    println!("🔍 Window '{}' is focused", label);
                    return Ok(true);
                }
            }
        }
    }
    
    println!("🔍 No Covalent window is focused");
    Ok(false)
}

#[tauri::command]
fn get_mcp_integrations() -> Result<Vec<serde_json::Value>, String> {
    // TODO: Fetch actual MCP integrations from Composio/backend
    println!("🔌 Fetching MCP integrations");
    Ok(vec![
        serde_json::json!({
            "id": "filesystem",
            "name": "Filesystem",
            "connected": false,
            "description": "Access and manage local files and folders"
        }),
        serde_json::json!({
            "id": "github",
            "name": "GitHub",
            "connected": false,
            "description": "Manage repositories, issues, and pull requests"
        }),
        serde_json::json!({
            "id": "perplexity",
            "name": "Perplexity Search",
            "connected": true,
            "description": "AI-powered web search — included by default"
        }),
        serde_json::json!({
            "id": "notion",
            "name": "Notion",
            "connected": false,
            "description": "Access and manage Notion pages and databases"
        }),
        serde_json::json!({
            "id": "gsuite",
            "name": "Google Workspace",
            "connected": false,
            "description": "Calendar, Drive, and Gmail integration"
        }),
    ])
}

// #[cfg(target_os = "macos")]
// use tauri_plugin_macos_permissions;

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    // In dev mode, load .env from CWD (project root). 
    // In production, we load from resource_dir inside .setup() below.
    if cfg!(dev) {
        if let Err(e) = dotenvy::dotenv() {
            eprintln!("⚠️  Warning: Could not load .env file: {}", e);
            eprintln!("   Make sure ANTHROPIC_API_KEY is set in your environment or .env file");
        } else {
            println!("✓ Loaded environment variables from .env file");
        }
    }
    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_updater::Builder::new().build())
        .plugin(tauri_plugin_notification::init())
        .plugin(tauri_plugin_process::init())
        .plugin(tauri_plugin_dialog::init())
        .setup(|app| {
            let is_dev = cfg!(dev);
            let app_dir = if is_dev {
                std::env::current_dir()
                    .unwrap()
                    .parent()
                    .unwrap()
                    .to_path_buf()
            } else {
                app.path()
                    .resource_dir()
                    .unwrap_or_else(|_| std::env::current_dir().unwrap())
            };
            
            println!("App directory: {:?} (dev={})", app_dir, is_dev);

            // In production, load .env from the resource directory into the Rust process
            if !is_dev {
                let env_file = app_dir.join(".env");
                if env_file.exists() {
                    match dotenvy::from_path(&env_file) {
                        Ok(_) => println!("✓ Loaded .env from resource dir: {:?}", env_file),
                        Err(e) => eprintln!("⚠️  Failed to load .env from {:?}: {}", env_file, e),
                    }
                } else {
                    eprintln!("⚠️  No .env found at {:?}", env_file);
                }
            }

            // Compute writable data directory for the database.
            // In dev: None (servers use their default project-relative paths).
            // In production: ~/Library/Application Support/com.hem.src-tauri/
            let data_dir: Option<PathBuf> = if is_dev {
                None
            } else {
                match app.path().app_data_dir() {
                    Ok(dir) => {
                        if let Err(e) = std::fs::create_dir_all(&dir) {
                            eprintln!("⚠️  Failed to create data dir {:?}: {}", dir, e);
                        }
                        println!("📁 Production data directory: {:?}", dir);
                        Some(dir)
                    }
                    Err(e) => {
                        eprintln!("⚠️  Could not resolve app data dir: {}", e);
                        None
                    }
                }
            };

            // In dev mode, MANUAL_SERVERS=1 skips spawning bundled servers
            // so you can run `python server/app.py` and `python run_mcp.py` yourself.
            let manual_servers = is_dev && std::env::var("MANUAL_SERVERS").unwrap_or_default() == "1";

            if manual_servers {
                println!("⏭️  MANUAL_SERVERS=1 — skipping bundled server startup");
                println!("   Start servers yourself:");
                println!("     python run_mcp.py");
                println!("     python server/app.py");
            }

            let mcp_server = McpServer::new();
            if !manual_servers {
                match mcp_server.start(app_dir.clone(), is_dev, data_dir.as_ref()) {
                    Ok(_) => println!("✓ MCP server started successfully"),
                    Err(e) => eprintln!("✗ Failed to start MCP server: {}", e),
                }
            }
            app.manage(mcp_server);

            let flask_server = FlaskServer::new();
            if !manual_servers {
                match flask_server.start(app_dir.clone(), is_dev, data_dir.as_ref()) {
                    Ok(_) => println!("✓ Flask server started successfully"),
                    Err(e) => eprintln!("✗ Failed to start Flask server: {}", e),
                }
            }
            app.manage(flask_server);

            println!("Starting Ollama serve...");
            let ollama_server = OllamaServer::new();
            match ollama_server.start() {
                Ok(_) => {},
                Err(e) => eprintln!("Ollama startup issue: {}", e),
            }
            app.manage(ollama_server);
            
            // Create and manage context state
            let context_state = ContextState::new();

            // Load excluded apps from settings (or seed defaults on first run)
            {
                let handle = app.handle().clone();
                let settings = load_settings(&handle);
                let excluded = if let Some(arr) = settings.get("excluded_apps").and_then(|v| v.as_array()) {
                    arr.iter()
                        .filter_map(|v| v.as_str().map(|s| s.to_string()))
                        .collect::<Vec<String>>()
                } else {
                    // First-run defaults — privacy-sensitive apps are blocked out of the box
                    let defaults = vec![
                        "Keychain Access".to_string(),
                        "Passwords".to_string(),
                        "1Password".to_string(),
                        "Bitwarden".to_string(),
                        "LastPass".to_string(),
                        "Dashlane".to_string(),
                        "1Password 7 - Password Manager".to_string(),
                    ];
                    // Persist defaults so the UI reflects them immediately
                    let json_arr = serde_json::Value::Array(
                        defaults.iter().map(|s| serde_json::Value::String(s.clone())).collect(),
                    );
                    save_setting(&handle, "excluded_apps", json_arr);
                    println!("🔒 Seeded default excluded apps ({} entries)", defaults.len());
                    defaults
                };
                context_state.set_excluded_apps_list(excluded.clone());
                println!("🔒 Excluded apps loaded: {:?}", excluded);
            }

            app.manage(context_state.clone());
            
            // Create and manage actions store
            let actions_store = ActionsStore::new();
            app.manage(actions_store.clone());
            
            // Start context collection loop using Tauri's async runtime
            println!("🚀 Starting context loop spawn task...");
            let context_state_for_loop = context_state.clone();
            let actions_store_for_loop = actions_store.clone();
            tauri::async_runtime::spawn(async move {
                match screen_context::ContextLoop::new_with_state_and_store(context_state_for_loop, actions_store_for_loop) {
                    Ok(mut context_loop) => {
                        println!("🔄 Initializing context loop...");
                        
                        if let Err(e) = context_loop.initialize().await {
                            eprintln!("✗ Failed to initialize context loop: {}", e);
                            return;
                        }
                        
                        // Set interval to 2 seconds
                        context_loop.set_interval(2);
                        
                        println!("✓ Context loop initialized successfully, starting loop...");
                        
                        // Run the loop (this will run indefinitely)
                        if let Err(e) = context_loop.run().await {
                            eprintln!("✗ Context loop error: {}", e);
                        }
                    }
                    Err(e) => {
                        eprintln!("✗ Failed to create context loop: {}", e);
                    }
                }
            });
            
            // Initialize tab completion system
            println!("⌨️  Initializing tab completion system...");
            let graph_db_path = if let Some(ref dir) = data_dir {
                dir.join("graph.db")
            } else {
                app_dir.clone().join("context-engine/graph.db")
            };
            let graph_db_path_str = graph_db_path.to_string_lossy().to_string();
            
            match tab_completion::initialize(graph_db_path_str) {
                Ok(trigger) => {
                    println!("✓ Tab completion system initialized");
                    
                    // Create window manager for ghost text and popup
                    let window_manager = std::sync::Arc::new(
                        tab_completion::CompletionWindowManager::new(app.handle().clone())
                    );
                    
                    // Create hotkey handler
                    let hotkey_handler = std::sync::Arc::new(tab_completion::HotkeyHandler::new());
                    
                    // Set up callback to show suggestions via window manager
                    // IMPORTANT: This callback is invoked from a background thread, but Tauri/Cocoa
                    // window operations MUST run on the main thread. We use run_on_main_thread to dispatch.
                    let window_manager_clone = window_manager.clone();
                    let hotkey_handler_clone = hotkey_handler.clone();
                    let app_handle_for_callback = app.handle().clone();
                    trigger.set_suggestion_callback(move |suggestion| {
                        // Wrap in catch_unwind to prevent silent thread death.
                        let hh = hotkey_handler_clone.clone();
                        let wm = window_manager_clone.clone();
                        let ah = app_handle_for_callback.clone();
                        let result = std::panic::catch_unwind(std::panic::AssertUnwindSafe(move || {
                            eprintln!("📤 [popup] Suggestion callback fired");

                            // IMPORTANT: Do NOT call hh.set_suggestion() here on the prediction
                            // thread. After an accept, the CGEventTap hotkey thread is actively
                            // processing rapid key events and briefly holds the same parking_lot
                            // mutexes inside HotkeyHandler. This creates a deadlock: the prediction
                            // thread blocks on hh.set_suggestion() while the CGEventTap thread
                            // cycles through its locks, but new key events keep arriving and the
                            // prediction thread never gets a turn.
                            //
                            // Fix: dispatch BOTH set_suggestion and show_suggestion to the main
                            // thread. The main thread is never the CGEventTap thread, so there is
                            // no lock contention. The main thread holds HotkeyHandler locks for
                            // only microseconds; the CGEventTap thread contends briefly but never
                            // deadlocks.
                            let window_manager = wm.clone();
                            let suggestion_clone = suggestion.clone();
                            let preview: String = suggestion.text.chars().take(30).collect();
                            eprintln!("📤 [popup 1/2] Dispatching to main thread for: {}...", preview);
                            if let Err(e) = ah.run_on_main_thread(move || {
                                eprintln!("📤 [popup 2/2] Main thread: set_suggestion + show_suggestion");
                                // Set suggestion on main thread to avoid deadlock with CGEventTap
                                hh.set_suggestion(Some(suggestion_clone.text.clone()));
                                if let Err(e) = window_manager.show_suggestion(&suggestion_clone) {
                                    eprintln!("⚠️  Failed to show completion: {}", e);
                                }
                            }) {
                                eprintln!("⚠️  Failed to dispatch to main thread: {}", e);
                            }
                        }));

                        if let Err(panic_info) = result {
                            eprintln!("🔴 PANIC in suggestion callback: {:?}", panic_info);
                        }
                    });
                    
                    // Set up hotkey callbacks
                    // NOTE: These callbacks are invoked from the CGEventTap thread (background thread).
                    // inject_completion_text uses CGEvent which is thread-safe, but hide_all() touches
                    // Tauri windows which require main thread execution.
                    let window_manager_accept = window_manager.clone();
                    let app_handle_for_accept = app.handle().clone();
                    let trigger_for_accept = trigger.clone();
                    hotkey_handler.set_accept_callback(move |text, chars_typed_during_grace| {
                        // Wrap entire callback in catch_unwind for safety
                        let text_clone = text.clone();
                        let trigger_clone = trigger_for_accept.clone();
                        let wm_clone = window_manager_accept.clone();
                        let app_handle_clone = app_handle_for_accept.clone();

                        let result = std::panic::catch_unwind(std::panic::AssertUnwindSafe(move || {
                            eprintln!("🔵 Accept callback: computing overlap...");
                            
                            // Get buffer suffix to detect overlap with prediction
                            // Must do this BEFORE spawning thread while we still have sync access
                            let buffer_suffix = trigger_clone.get_buffer_suffix(text_clone.len());

                            // Find overlap between what user typed and what prediction contains
                            let overlap = find_overlap(&buffer_suffix, &text_clone);

                            // Total chars to erase = overlap + chars typed during grace period
                            let total_erase = overlap + chars_typed_during_grace;

                            println!("✅ Accepting completion via hotkey (overlap: {}, grace: {}, total erase: {})",
                                     overlap, chars_typed_during_grace, total_erase);

                            eprintln!("🔵 Accept callback: spawning accept thread...");

                            // IMPORTANT: Spawn a thread to handle the accept logic.
                            // The callback runs inside CGEventTap which must return quickly.
                            // inject_with_backspace has 150ms+ of sleeps that would block the tap.
                            let wm = wm_clone.clone();
                            let app_handle = app_handle_clone.clone();
                            let trigger = trigger_clone.clone();
                            let text = text_clone.clone();

                            std::thread::spawn(move || {
                                // Wrap the entire thread in catch_unwind
                                let result = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| {
                                    println!("🧵 Accept thread started");

                                    // Wait for user to release Option key before injecting.
                                    // Option+Tab accept fires while Option is still physically held;
                                    // if we inject immediately, AppleScript's Cmd+V paste could be
                                    // interpreted as Cmd+Option+V in some apps.
                                    std::thread::sleep(std::time::Duration::from_millis(150));

                                    // Inject the text with backspace for overlap + grace period chars
                                    println!("🧵 Injecting text...");
                                    if let Err(e) = tab_completion::injector::inject_with_backspace(text.clone(), total_erase) {
                                        eprintln!("⚠️  Failed to inject text: {}", e);
                                    }
                                    println!("🧵 Text injection complete");

                                    // Hide completion windows BEFORE triggering new prediction
                                    // This prevents race condition where hide_all interferes with new show_suggestion
                                    println!("🧵 Hiding windows...");
                                    let wm_clone = wm.clone();
                                    let app_handle_clone = app_handle.clone();
                                    let _ = app_handle_clone.run_on_main_thread(move || {
                                        println!("🧵 [main thread] Hiding all windows");
                                        let _ = wm_clone.hide_all();
                                    });

                                    // Small delay to ensure hide completes before new prediction cycle
                                    std::thread::sleep(std::time::Duration::from_millis(50));

                                    // Erase overlap + grace chars from buffer to keep it in sync with terminal.
                                    // The injector already erased these chars from the terminal via backspaces;
                                    // without this, the buffer accumulates duplicate chars (e.g. "git aadd"
                                    // instead of "git add") and all subsequent predictions are garbage.
                                    trigger.erase_from_buffer(total_erase);

                                    // Update the trigger's buffer with the accepted text and re-trigger prediction
                                    // NOTE: This spawns a thread with 300ms delay, then shows popup if prediction found
                                    println!("🧵 Calling append_to_buffer...");
                                    trigger.append_to_buffer(text.clone());
                                    println!("🧵 Accept thread complete");
                                }));
                                
                                if let Err(e) = result {
                                    eprintln!("🔴 PANIC in accept thread: {:?}", e);
                                }
                            });

                            eprintln!("🔵 Accept callback: thread spawned, returning");
                        }));

                        if let Err(e) = result {
                            eprintln!("🔴 PANIC in accept callback outer: {:?}", e);
                        }
                    });

                    let window_manager_dismiss = window_manager.clone();
                    let app_handle_for_dismiss = app.handle().clone();
                    hotkey_handler.set_dismiss_callback(move || {
                        println!("❌ Dismissing completion via hotkey");
                        // Hide all completion windows - must run on main thread
                        let wm = window_manager_dismiss.clone();
                        let _ = app_handle_for_dismiss.run_on_main_thread(move || {
                            let _ = wm.hide_all();
                        });
                    });

                    // Set up enhanced dismiss callback for retry predictions
                    let trigger_for_dismiss = trigger.clone();
                    let window_manager_dismiss_enhanced = window_manager.clone();
                    let app_handle_for_dismiss_enhanced = app.handle().clone();
                    hotkey_handler.set_dismiss_with_info_callback(move |dismiss_info| {
                        println!("🔄 Dismiss with info - triggering retry prediction");
                        let dismissed_preview: String = dismiss_info.dismissed_text.chars().take(30).collect();
                        println!("   Dismissed: {}...", dismissed_preview);
                        println!("   Chars typed after: '{}'", dismiss_info.chars_typed_after);
                        println!("   Time shown: {}ms", dismiss_info.time_shown_ms);

                        // Hide windows first
                        let wm = window_manager_dismiss_enhanced.clone();
                        let _ = app_handle_for_dismiss_enhanced.run_on_main_thread(move || {
                            let _ = wm.hide_all();
                        });

                        // Trigger retry prediction with decline context
                        trigger_for_dismiss.handle_decline(
                            dismiss_info.dismissed_text,
                            dismiss_info.time_shown_ms,
                            dismiss_info.chars_typed_after,
                        );
                    });

                    // Set up actions getter for enriched predictions
                    let actions_store_for_trigger = actions_store.clone();
                    trigger.set_actions_getter(move || {
                        let actions = actions_store_for_trigger.get_actions();
                        actions.into_iter().map(|a| {
                            tab_completion::ActionSummary::new(a.title, a.description)
                        }).collect()
                    });
                    
                    // Start hotkey listener
                    if let Err(e) = hotkey_handler.clone().start_listening() {
                        eprintln!("⚠️  Failed to start hotkey listener: {}", e);
                        eprintln!("   Hotkeys will not be available");
                    }
                    
                    // Restore persisted tab completion enabled/disabled state
                    {
                        let settings = load_settings(app.handle());
                        let persisted = settings
                            .get("tab_completion_enabled")
                            .and_then(|v| v.as_bool())
                            .unwrap_or(false); // default OFF
                        trigger.set_tab_completion_enabled(persisted);
                        println!(
                            "⚙️  Tab completion restored from settings: {}",
                            if persisted { "ON" } else { "OFF" }
                        );
                    }

                    // Start listening for keystrokes
                    let trigger_clone = trigger.clone();
                    trigger_clone.start_listening();
                    
                    // Store trigger, hotkey handler, and window manager in app state
                    app.manage(trigger);
                    app.manage(hotkey_handler);
                    app.manage(window_manager);
                    
                    println!("✓ Tab completion listener started");
                }
                Err(e) => {
                    eprintln!("✗ Failed to initialize tab completion: {}", e);
                    eprintln!("   Tab completion will not be available");
                }
            }
            
            // Create menu items
            let open_dashboard = MenuItem::with_id(app, "open_dashboard", "Dashboard", true, Some("cmd+;"))?;
            let quit = PredefinedMenuItem::quit(app, Some("Quit"))?;
            
            // Create Profile submenu
            let profile_submenu = Submenu::with_items(
                app,
                "Profile",
                true,
                &[&open_dashboard, &quit],
            )?;
            
            // Create menu bar
            let menu = Menu::with_items(app, &[&profile_submenu])?;
            
            // Set menu
            app.set_menu(menu)?;
            
            // Handle menu events
            app.on_menu_event(move |app, event| {
                match event.id().as_ref() {
                    "open_dashboard" => {
                        println!("🎛️  Opening dashboard");
                        if let Some(window) = app.get_webview_window("dashboard") {
                            let _ = window.show();
                            let _ = window.set_focus();
                        } else {
                            eprintln!("⚠️  Dashboard window not found");
                        }
                    }
                    _ => {}
                }
            });
            
            Ok(())
        })
        .on_window_event(|window, event| {
            // Prevent the dashboard window from being destroyed when closed
            // Instead, just hide it so it can be reopened later
            if window.label() == "dashboard" {
                if let tauri::WindowEvent::CloseRequested { api, .. } = event {
                    println!("🎛️  Hiding dashboard window instead of closing");
                    let _ = window.hide();
                    api.prevent_close();
                }
            }
        })
        .invoke_handler(tauri::generate_handler![
            greet, 
            toggle_profile, 
            toggle_link_mcps,
            toggle_context_collection,
            enable_context_collection,
            disable_context_collection,
            get_context_collection_status,
            enable_context_collection_if_not_user_paused,
            get_tab_completion_status,
            set_tab_completion_enabled,
            toggle_tab_completion,
            plan_action,
            execute_action,
            edit_action,
            get_suggested_actions,
            clear_suggested_actions,
            tab_completion::injector::inject_completion_text,
            get_cursor_position,
            get_cache_state,
            get_actions_history,
            get_memory_graph_data,
            get_excluded_apps,
            set_excluded_apps,
            get_auth_status,
            get_mcp_integrations,
            open_dashboard_history,
            open_main_window,
            is_covalent_focused
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
