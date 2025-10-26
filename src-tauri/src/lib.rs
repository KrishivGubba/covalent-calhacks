// Module declarations
pub mod screen_context;
use tauri::menu::{Menu, MenuItem, PredefinedMenuItem, Submenu};
use tauri::Manager;
use std::process::{Child, Command};
use std::sync::{Arc, Mutex};
use std::path::PathBuf;

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

// #[cfg(target_os = "macos")]
// use tauri_plugin_macos_permissions;

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .setup(|app| {
            // Start Flask server
            let app_dir = app.path()
                .resource_dir()
                .unwrap_or_else(|_| {
                    // Fallback to current working directory in dev mode
                    std::env::current_dir()
                        .unwrap()
                        .parent()
                        .unwrap()
                        .to_path_buf()
                });
            
            let flask_server = FlaskServer::new();
            
            match flask_server.start(app_dir) {
                Ok(_) => println!("✓ Flask server started successfully"),
                Err(e) => eprintln!("✗ Failed to start Flask server: {}", e),
            }
            
            // Store flask server in app state so it stays alive
            app.manage(flask_server);
            
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
        .invoke_handler(tauri::generate_handler![greet, toggle_profile, toggle_link_mcps])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
