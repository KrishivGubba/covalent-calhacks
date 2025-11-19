// Module declarations
pub mod screen_context;
use tauri::menu::{Menu, MenuItem, PredefinedMenuItem, Submenu};
use tauri::Manager;
use std::process::{Child, Command};
use std::sync::{Arc, Mutex, atomic::{AtomicBool, Ordering}};
use std::path::PathBuf;

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
    
    // Re-enable context collection after action completes
    // Note: You may want to add a delay here to avoid immediate re-collection
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
            
            match flask_server.start(app_dir) {
                Ok(_) => println!("✓ Flask server started successfully"),
                Err(e) => eprintln!("✗ Failed to start Flask server: {}", e),
            }
            
            // Store flask server in app state so it stays alive
            app.manage(flask_server);
            
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
            
            // Create menu items
            let open_profile = MenuItem::with_id(app, "open_profile", "Open Profile", true, None::<&str>)?;
            let link_mcps = MenuItem::with_id(app, "link_mcps", "Link MCPs", true, None::<&str>)?;
            let quit = PredefinedMenuItem::quit(app, Some("Quit"))?;
            
            // Create Profile submenu
            let profile_submenu = Submenu::with_items(
                app,
                "Profile",
                true,
                &[&open_profile, &link_mcps, &quit],
            )?;
            
            // Create menu bar
            let menu = Menu::with_items(app, &[&profile_submenu])?;
            
            // Set menu
            app.set_menu(menu)?;
            
            // Handle menu events
            app.on_menu_event(move |_app, event| {
                match event.id().as_ref() {
                    "open_profile" => {
                        println!("Open Profile clicked");
                        // TODO: Implement profile functionality
                    }
                    "link_mcps" => {
                        println!("Link MCPs clicked");
                        // TODO: Implement MCP linking functionality
                    }
                    _ => {}
                }
            });
            
            Ok(())
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
            get_suggested_actions,
            clear_suggested_actions
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
