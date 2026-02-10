// Module declarations
pub mod ai_provider;
pub mod screen_context;
pub mod tab_completion;
use tauri::menu::{Menu, MenuItem, PredefinedMenuItem, Submenu};
use tauri::{Manager, Emitter};
use std::process::{Child, Command};
use std::sync::{Arc, Mutex, atomic::{AtomicBool, Ordering}};
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
    pub description: String,     // action_plan from Flask
    pub action_prompt: String,   // action_prompt from Flask
}

// Context collection state - controls whether context is being collected and sent
#[derive(Clone)]
pub struct ContextState {
    // Controls whether context collection is active
    // Set to false to pause context collection (e.g., when actions are running, app is in focus, or user toggles)
    pub is_enabled: Arc<AtomicBool>,
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

    pub fn update_action(&self, action_uuid: &str, title: String, description: String, action_prompt: String) {
        if let Ok(mut actions) = self.actions.lock() {
            if let Some(action) = actions.iter_mut().find(|a| a.uuid == action_uuid) {
                action.title = title;
                action.description = description;
                action.action_prompt = action_prompt;
                println!("✏️  Updated action in store: {}", action_uuid);
            }
        }
    }
}

impl ContextState {
    fn new() -> Self {
        Self {
            is_enabled: Arc::new(AtomicBool::new(true)), // Enabled by default
        }
    }

    pub fn is_enabled(&self) -> bool {
        self.is_enabled.load(Ordering::Relaxed)
    }

    pub fn enable(&self) {
        println!("🟢 Context collection ENABLED");
        self.is_enabled.store(true, Ordering::Relaxed);
    }

    pub fn disable(&self) {
        println!("🔴 Context collection DISABLED");
        self.is_enabled.store(false, Ordering::Relaxed);
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

// Flask server state management
struct FlaskServer {
    process: Arc<Mutex<Option<Child>>>,
}

impl FlaskServer {
    fn new() -> Self {
        Self {
            process: Arc::new(Mutex::new(None)),
        }
    }

    fn start(&self, app_dir: PathBuf) -> Result<(), String> {
        let server_dir = app_dir.join("server");
        let start_script = server_dir.join("start_server.sh");
        
        if !start_script.exists() {
            return Err(format!("Flask start script not found at {:?}", start_script));
        }

        println!("Starting Flask server from {:?}", start_script);
        
        match Command::new("bash")
            .arg(&start_script)
            .current_dir(&server_dir)
            .spawn()
        {
            Ok(child) => {
                println!("Flask server started with PID: {:?}", child.id());
                let mut process_guard = self.process.lock().unwrap();
                *process_guard = Some(child);
                
                // Give server a moment to start up
                std::thread::sleep(std::time::Duration::from_secs(2));
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
    state.enable();
}

#[tauri::command]
fn disable_context_collection(state: tauri::State<ContextState>) {
    state.disable();
}

#[tauri::command]
fn get_context_collection_status(state: tauri::State<ContextState>) -> bool {
    state.is_enabled()
}

// Trigger action command
#[tauri::command]
async fn trigger_action(action_uuid: String, action_prompt: String, state: tauri::State<'_, ContextState>) -> Result<serde_json::Value, String> {
    use screen_context::ContextApiClient;
    
    println!("🎬 Triggering action: {} ({})", action_prompt, action_uuid);
    
    // Disable context collection during action execution to prevent feedback loops
    state.disable();
    
    let api_client = ContextApiClient::new();
    
    let result = api_client
        .trigger_action(action_uuid, action_prompt)
        .await
        .map_err(|e| format!("Failed to trigger action: {}", e));
    
    // Print the result from Flask/Composio
    match &result {
        Ok(response) => {
            println!("✅ Action execution response:");
            println!("{}", serde_json::to_string_pretty(response).unwrap_or_else(|_| format!("{:?}", response)));
        }
        Err(e) => {
            println!("❌ Action execution failed: {}", e);
        }
    }
    
    // Re-enable context collection after action completes
    // Note: You may want to add a delay here to avoid immediate re-collection
    tokio::time::sleep(tokio::time::Duration::from_secs(2)).await;
    state.enable();
    
    result
}

// Edit action command (optional persistence)
#[tauri::command]
async fn edit_action(
    action_uuid: String,
    action_name: String,
    action_plan: String,
    action_prompt: String,
    persist: bool,
    store: tauri::State<'_, ActionsStore>
) -> Result<serde_json::Value, String> {
    use screen_context::ContextApiClient;

    println!("✏️  Editing action: {} (persist: {})", action_uuid, persist);

    let api_client = ContextApiClient::new();
    let result = api_client
        .edit_action(action_uuid.clone(), action_name.clone(), action_plan.clone(), action_prompt.clone(), persist)
        .await
        .map_err(|e| format!("Failed to edit action: {}", e));

    if persist {
        store.update_action(&action_uuid, action_name, action_plan, action_prompt);
    }

    result
}

// Trigger action with override command
#[tauri::command]
async fn trigger_action_with_override(
    action_uuid: String,
    action_name: String,
    action_plan: String,
    action_prompt: String,
    state: tauri::State<'_, ContextState>
) -> Result<serde_json::Value, String> {
    use screen_context::ContextApiClient;

    println!("🎬 Triggering action with override: {} ({})", action_name, action_uuid);

    // Disable context collection during action execution to prevent feedback loops
    state.disable();

    let api_client = ContextApiClient::new();
    let result = api_client
        .trigger_action_with_override(action_uuid, action_name, action_plan, action_prompt)
        .await
        .map_err(|e| format!("Failed to trigger action: {}", e));

    match &result {
        Ok(response) => {
            println!("✅ Action execution response:");
            println!("{}", serde_json::to_string_pretty(response).unwrap_or_else(|_| format!("{:?}", response)));
        }
        Err(e) => {
            println!("❌ Action execution failed: {}", e);
        }
    }

    tokio::time::sleep(tokio::time::Duration::from_secs(2)).await;
    state.enable();

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
fn get_excluded_apps() -> Result<Vec<String>, String> {
    // TODO: Read from settings/config
    println!("🔒 Fetching excluded apps");
    Ok(vec![])
}

#[tauri::command]
fn set_excluded_apps(apps: Vec<String>) -> Result<(), String> {
    // TODO: Save to settings/config
    println!("🔒 Setting excluded apps: {:?}", apps);
    Ok(())
}

#[tauri::command]
fn get_auth_status() -> Result<serde_json::Value, String> {
    // TODO: Implement actual auth status check
    println!("🔐 Checking auth status");
    Ok(serde_json::json!({
        "authenticated": false,
        "user": null,
        "message": "Authentication not yet implemented"
    }))
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
    // Load environment variables from .env file
    if let Err(e) = dotenvy::dotenv() {
        eprintln!("⚠️  Warning: Could not load .env file: {}", e);
        eprintln!("   Make sure ANTHROPIC_API_KEY is set in your environment or .env file");
    } else {
        println!("✓ Loaded environment variables from .env file");
    }
    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_updater::Builder::new().build())
        .plugin(tauri_plugin_notification::init())
        .plugin(tauri_plugin_process::init())
        .setup(|app| {
            // Start Flask server
            let app_dir = if cfg!(dev) {
                // In dev mode, use project root (parent of src-tauri)
                std::env::current_dir()
                    .unwrap()
                    .parent()
                    .unwrap()
                    .to_path_buf()
            } else {
                // In production, use resource directory
                app.path()
                    .resource_dir()
                    .unwrap_or_else(|_| std::env::current_dir().unwrap())
            };
            
            println!("App directory: {:?}", app_dir);
            
            let flask_server = FlaskServer::new();
            
            match flask_server.start(app_dir.clone()) {
                Ok(_) => println!("✓ Flask server started successfully"),
                Err(e) => eprintln!("✗ Failed to start Flask server: {}", e),
            }

            // Store flask server in app state so it stays alive
            app.manage(flask_server);

            // Start Ollama serve (for local LLM inference)
            println!("🦙 Starting Ollama serve...");
            let ollama_server = OllamaServer::new();
            match ollama_server.start() {
                Ok(_) => {},
                Err(e) => eprintln!("⚠️  Ollama startup issue: {}", e),
            }
            // Store ollama server in app state so it gets cleaned up on exit
            app.manage(ollama_server);
            
            // Create and manage context state
            let context_state = ContextState::new();
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
            let graph_db_path = app_dir.clone().join("server/graph.db");
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
                        println!("📤 Showing completion suggestion");

                        // Update hotkey handler with new suggestion (this is thread-safe via parking_lot::Mutex)
                        hotkey_handler_clone.set_suggestion(Some(suggestion.text.clone()));

                        // Dispatch UI operations to main thread to prevent crashes
                        let window_manager = window_manager_clone.clone();
                        let suggestion_clone = suggestion.clone();
                        let suggestion_text_for_log = suggestion.text.clone();
                        println!("📤 Dispatching show_suggestion to main thread for: {}...",
                                 &suggestion_text_for_log[..suggestion_text_for_log.len().min(30)]);
                        if let Err(e) = app_handle_for_callback.run_on_main_thread(move || {
                            println!("🔄 Main thread executing show_suggestion");
                            // Show suggestion using window manager (ghost text or popup)
                            if let Err(e) = window_manager.show_suggestion(&suggestion_clone) {
                                eprintln!("⚠️  Failed to show completion: {}", e);
                            }
                        }) {
                            eprintln!("⚠️  Failed to dispatch to main thread: {}", e);
                        } else {
                            println!("✅ Dispatch queued successfully");
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
                        // Get buffer suffix to detect overlap with prediction
                        // Must do this BEFORE spawning thread while we still have sync access
                        let buffer_suffix = trigger_for_accept.get_buffer_suffix(text.len());

                        // Find overlap between what user typed and what prediction contains
                        let overlap = find_overlap(&buffer_suffix, &text);

                        // Total chars to erase = overlap + chars typed during grace period
                        let total_erase = overlap + chars_typed_during_grace;

                        println!("✅ Accepting completion via hotkey (overlap: {}, grace: {}, total erase: {})",
                                 overlap, chars_typed_during_grace, total_erase);

                        // IMPORTANT: Spawn a thread to handle the accept logic.
                        // The callback runs inside CGEventTap which must return quickly.
                        // inject_with_backspace has 150ms+ of sleeps that would block the tap.
                        let wm = window_manager_accept.clone();
                        let app_handle = app_handle_for_accept.clone();
                        let trigger = trigger_for_accept.clone();

                        std::thread::spawn(move || {
                            println!("🧵 Accept thread started");

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

                            // Update the trigger's buffer with the accepted text and re-trigger prediction
                            // NOTE: This spawns a thread with 300ms delay, then shows popup if prediction found
                            println!("🧵 Calling append_to_buffer...");
                            trigger.append_to_buffer(text.clone());
                            println!("🧵 Accept thread complete");
                        });
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
                        println!("   Dismissed: {}...", &dismiss_info.dismissed_text[..dismiss_info.dismissed_text.len().min(30)]);
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
            let open_profile = MenuItem::with_id(app, "open_profile", "Open Profile", true, None::<&str>)?;
            let link_mcps = MenuItem::with_id(app, "link_mcps", "Link MCPs", true, None::<&str>)?;
            let open_dashboard = MenuItem::with_id(app, "open_dashboard", "Dashboard", true, Some("cmd+;"))?;
            let quit = PredefinedMenuItem::quit(app, Some("Quit"))?;
            
            // Create Profile submenu
            let profile_submenu = Submenu::with_items(
                app,
                "Profile",
                true,
                &[&open_profile, &link_mcps, &open_dashboard, &quit],
            )?;
            
            // Create menu bar
            let menu = Menu::with_items(app, &[&profile_submenu])?;
            
            // Set menu
            app.set_menu(menu)?;
            
            // Handle menu events
            app.on_menu_event(move |app, event| {
                match event.id().as_ref() {
                    "open_profile" => {
                        println!("Open Profile clicked");
                        // TODO: Implement profile functionality
                    }
                    "link_mcps" => {
                        println!("Link MCPs clicked");
                        // TODO: Implement MCP linking functionality
                    }
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
            trigger_action,
            edit_action,
            trigger_action_with_override,
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
            get_mcp_integrations
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
