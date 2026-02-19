use anyhow::{Context as AnyhowContext, Result};
use futures::{SinkExt, StreamExt};
use reqwest::Client;
use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::collections::HashMap;
use std::sync::atomic::AtomicU64;
use std::sync::Arc;
use std::time::Duration;
use tokio::sync::Mutex;
use tokio::time::timeout;
use tokio_tungstenite::{connect_async, tungstenite::Message};

use crate::screen_context::context_data::{
    DOMData, FormData, InputData, LinkData, ScrollPosition, ViewportSize,
};

#[allow(dead_code)]
#[derive(Debug, Clone, Serialize, Deserialize)]
struct DevToolsTab {
    id: String,
    title: String,
    url: String,
    #[serde(rename = "webSocketDebuggerUrl")]
    websocket_debugger_url: Option<String>,
    #[serde(rename = "type")]
    tab_type: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
struct DevToolsRequest {
    id: u64,
    method: String,
    params: Option<Value>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
struct DevToolsResponse {
    id: Option<u64>,
    result: Option<Value>,
    error: Option<Value>,
    method: Option<String>,
    params: Option<Value>,
}

#[allow(dead_code)]
pub struct ChromiumBridge {
    client: Client,
    debugging_port: u16,
    request_id: AtomicU64,
    connected_tab_id: Arc<Mutex<Option<String>>>,
}

impl ChromiumBridge {
    pub fn new() -> Self {
        Self {
            client: Client::new(),
            debugging_port: 9222, // Default Chrome debugging port
            request_id: AtomicU64::new(1),
            connected_tab_id: Arc::new(Mutex::new(None)),
        }
    }
    
    pub fn with_debugging_port(mut self, port: u16) -> Self {
        self.debugging_port = port;
        self
    }
    
    /// Check if Chrome DevTools is available
    pub async fn is_available(&self) -> bool {
        self.get_tabs().await.is_ok()
    }
    
    /// Get list of available tabs
    #[allow(private_interfaces)]
    pub async fn get_tabs(&self) -> Result<Vec<DevToolsTab>> {
        let url = format!("http://localhost:{}/json", self.debugging_port);
        
        let response = timeout(Duration::from_secs(2), self.client.get(&url).send())
            .await
            .context("Timeout connecting to Chrome DevTools")?
            .context("Failed to connect to Chrome DevTools")?;
        
        if !response.status().is_success() {
            return Err(anyhow::anyhow!(
                "Chrome DevTools returned status: {}",
                response.status()
            ));
        }
        
        let tabs: Vec<DevToolsTab> = response
            .json()
            .await
            .context("Failed to parse tabs response")?;
        
        Ok(tabs)
    }
    
    /// Extract comprehensive DOM context with change detection
    pub async fn extract_browser_context(&self) -> Result<DOMData> {
        let tabs = self.get_tabs().await?;
        
        if let Some(active_tab) = tabs.first() {
            self.extract_dom_data_from_tab(active_tab).await
        } else {
            Err(anyhow::anyhow!("No active browser tabs found"))
        }
    }
    
    /// Extract DOM data from a specific tab using WebSocket connection to Chrome DevTools
    async fn extract_dom_data_from_tab(&self, tab: &DevToolsTab) -> Result<DOMData> {
        // Get WebSocket URL for this tab
        let ws_url = match &tab.websocket_debugger_url {
            Some(url) => url.clone(),
            None => {
                // Fallback to basic tab information if no WebSocket URL
                return Ok(self.create_basic_dom_data(tab));
            }
        };

        // JavaScript to extract comprehensive DOM data
        let js_code = r#"
            (() => {
                try {
                    const extractDOMData = () => {
                        const viewport = {
                            width: window.innerWidth,
                            height: window.innerHeight
                        };

                        const scroll = {
                            x: window.scrollX,
                            y: window.scrollY
                        };

                        // Extract visible text from body
                        const textNodes = [];
                        const walker = document.createTreeWalker(
                            document.body || document.documentElement,
                            NodeFilter.SHOW_TEXT,
                            null,
                            false
                        );

                        let node;
                        while (node = walker.nextNode()) {
                            const text = node.textContent.trim();
                            if (text.length > 0) {
                                textNodes.push(text);
                            }
                        }

                        // Extract forms
                        const forms = Array.from(document.forms || []).map(form => ({
                            action: form.action || '',
                            method: form.method || 'GET',
                            fields: Array.from(form.elements).map(el => el.name || el.id || '').filter(n => n),
                            hasFileUpload: Array.from(form.elements).some(el => el.type === 'file')
                        }));

                        // Extract inputs
                        const inputs = Array.from(document.querySelectorAll('input, textarea, select') || []).map(input => ({
                            inputType: input.type || input.tagName.toLowerCase(),
                            name: input.name || null,
                            placeholder: input.placeholder || null,
                            valueLength: (input.value || '').length,
                            isFocused: document.activeElement === input,
                            isRequired: input.required || false
                        }));

                        // Extract links
                        const links = Array.from(document.querySelectorAll('a[href]') || []).map(link => ({
                            text: link.textContent.trim(),
                            href: link.href,
                            isExternal: !link.href.startsWith(window.location.origin)
                        }));

                        // Extract buttons
                        const buttons = Array.from(document.querySelectorAll('button, input[type="button"], input[type="submit"]') || [])
                            .map(btn => btn.textContent || btn.value || 'Button')
                            .filter(text => text.trim());

                        // Get meta data
                        const metaData = {};
                        document.querySelectorAll('meta').forEach(meta => {
                            const name = meta.name || meta.property;
                            const content = meta.content;
                            if (name && content) {
                                metaData[name] = content;
                            }
                        });

                        return {
                            url: window.location.href,
                            title: document.title,
                            activeElement: document.activeElement ? document.activeElement.tagName : null,
                            forms: forms,
                            visibleText: textNodes.join(' ').substring(0, 5000),
                            buttons: buttons,
                            inputs: inputs,
                            links: links.slice(0, 50),
                            metaData: metaData,
                            scrollPosition: scroll,
                            viewportSize: viewport
                        };
                    };

                    return JSON.stringify(extractDOMData());
                } catch (e) {
                    return JSON.stringify({ error: e.message });
                }
            })()
        "#;

        // Use WebSocket to execute JavaScript via Chrome DevTools Protocol
        match self.execute_js_via_websocket(&ws_url, js_code).await {
            Ok(result_json) => {
                // Parse the JSON string result
                if let Ok(data) = serde_json::from_str::<Value>(&result_json) {
                    if data.get("error").is_some() {
                        eprintln!("⚠️  DOM extraction JS error: {:?}", data["error"]);
                        return Ok(self.create_basic_dom_data(tab));
                    }
                    return self.parse_dom_value(data, tab);
                }
                Ok(self.create_basic_dom_data(tab))
            }
            Err(e) => {
                eprintln!("⚠️  WebSocket DOM extraction failed: {}, using basic data", e);
                Ok(self.create_basic_dom_data(tab))
            }
        }
    }

    /// Execute JavaScript via WebSocket connection to Chrome DevTools
    async fn execute_js_via_websocket(&self, ws_url: &str, js_code: &str) -> Result<String> {
        // Connect to WebSocket with timeout
        let (ws_stream, _) = timeout(
            Duration::from_secs(3),
            connect_async(ws_url)
        ).await
            .context("WebSocket connection timeout")?
            .context("Failed to connect to Chrome DevTools WebSocket")?;

        let (mut write, mut read) = ws_stream.split();

        // Send Runtime.evaluate command
        let request_id = self.request_id.fetch_add(1, std::sync::atomic::Ordering::SeqCst);
        let request = serde_json::json!({
            "id": request_id,
            "method": "Runtime.evaluate",
            "params": {
                "expression": js_code,
                "returnByValue": true,
                "awaitPromise": false
            }
        });

        write.send(Message::Text(request.to_string())).await
            .context("Failed to send WebSocket message")?;

        // Wait for response with timeout
        let response = timeout(Duration::from_secs(5), async {
            while let Some(msg) = read.next().await {
                match msg {
                    Ok(Message::Text(text)) => {
                        if let Ok(response) = serde_json::from_str::<Value>(&text) {
                            if response.get("id") == Some(&Value::from(request_id)) {
                                return Ok(response);
                            }
                        }
                    }
                    Ok(Message::Close(_)) => break,
                    Err(e) => return Err(anyhow::anyhow!("WebSocket error: {}", e)),
                    _ => continue,
                }
            }
            Err(anyhow::anyhow!("WebSocket closed without response"))
        }).await
            .context("WebSocket response timeout")??;

        // Close the connection
        let _ = write.close().await;

        // Extract result
        if let Some(error) = response.get("error") {
            return Err(anyhow::anyhow!("DevTools error: {:?}", error));
        }

        if let Some(result) = response.get("result").and_then(|r| r.get("result")).and_then(|r| r.get("value")) {
            if let Some(s) = result.as_str() {
                return Ok(s.to_string());
            }
        }

        Err(anyhow::anyhow!("Unexpected response format"))
    }

    /// Create basic DOM data from tab info when JS execution fails
    fn create_basic_dom_data(&self, tab: &DevToolsTab) -> DOMData {
        DOMData {
            url: tab.url.clone(),
            title: tab.title.clone(),
            active_element: None,
            forms: Vec::new(),
            visible_text: String::new(), // Empty - don't fake it
            buttons: Vec::new(),
            inputs: Vec::new(),
            links: Vec::new(),
            meta_data: HashMap::new(),
            scroll_position: None,
            viewport_size: None,
            cookies: None,
        }
    }

    /// Parse DOM data from a Value (direct JSON, not wrapped in response)
    fn parse_dom_value(&self, data: Value, tab: &DevToolsTab) -> Result<DOMData> {
        if data.is_null() {
            return Ok(self.create_basic_dom_data(tab));
        }

        // Parse forms
        let forms: Vec<FormData> = data["forms"]
            .as_array()
            .unwrap_or(&vec![])
            .iter()
            .map(|f| FormData {
                action: f["action"].as_str().unwrap_or("").to_string(),
                method: f["method"].as_str().unwrap_or("GET").to_string(),
                fields: f["fields"]
                    .as_array()
                    .unwrap_or(&vec![])
                    .iter()
                    .map(|field| field.as_str().unwrap_or("").to_string())
                    .collect(),
                has_file_upload: f["hasFileUpload"].as_bool().unwrap_or(false),
            })
            .collect();

        // Parse inputs
        let inputs: Vec<InputData> = data["inputs"]
            .as_array()
            .unwrap_or(&vec![])
            .iter()
            .map(|i| InputData {
                input_type: i["inputType"].as_str().unwrap_or("").to_string(),
                name: i["name"].as_str().map(|s| s.to_string()),
                placeholder: i["placeholder"].as_str().map(|s| s.to_string()),
                value_length: i["valueLength"].as_u64().unwrap_or(0) as usize,
                is_focused: i["isFocused"].as_bool().unwrap_or(false),
                is_required: i["isRequired"].as_bool().unwrap_or(false),
            })
            .collect();

        // Parse links
        let links: Vec<LinkData> = data["links"]
            .as_array()
            .unwrap_or(&vec![])
            .iter()
            .map(|l| LinkData {
                text: l["text"].as_str().unwrap_or("").to_string(),
                href: l["href"].as_str().unwrap_or("").to_string(),
                is_external: l["isExternal"].as_bool().unwrap_or(false),
            })
            .collect();

        // Parse buttons
        let buttons: Vec<String> = data["buttons"]
            .as_array()
            .unwrap_or(&vec![])
            .iter()
            .map(|b| b.as_str().unwrap_or("").to_string())
            .collect();

        // Parse meta data
        let mut meta_data = HashMap::new();
        if let Some(meta_obj) = data["metaData"].as_object() {
            for (key, value) in meta_obj {
                if let Some(str_value) = value.as_str() {
                    meta_data.insert(key.clone(), str_value.to_string());
                }
            }
        }

        // Parse scroll position
        let scroll_position = if let Some(scroll) = data["scrollPosition"].as_object() {
            Some(ScrollPosition {
                x: scroll["x"].as_f64().unwrap_or(0.0),
                y: scroll["y"].as_f64().unwrap_or(0.0),
            })
        } else {
            None
        };

        // Parse viewport size
        let viewport_size = if let Some(viewport) = data["viewportSize"].as_object() {
            Some(ViewportSize {
                width: viewport["width"].as_u64().unwrap_or(0) as u32,
                height: viewport["height"].as_u64().unwrap_or(0) as u32,
            })
        } else {
            None
        };

        Ok(DOMData {
            url: data["url"].as_str().unwrap_or(&tab.url).to_string(),
            title: data["title"].as_str().unwrap_or(&tab.title).to_string(),
            active_element: data["activeElement"].as_str().map(|s| s.to_string()),
            forms,
            visible_text: data["visibleText"].as_str().unwrap_or("").to_string(),
            buttons,
            inputs,
            links,
            meta_data,
            scroll_position,
            viewport_size,
            cookies: None,
        })
    }

    /// Parse DOM response from DevTools (legacy method for HTTP API fallback)
    #[allow(dead_code)]
    fn parse_dom_response(&self, response: Value, tab: &DevToolsTab) -> Result<DOMData> {
        let data = response["result"]["value"].clone();
        self.parse_dom_value(data, tab)
    }
    
    /// Get current page URL
    pub async fn get_current_url(&self) -> Result<String> {
        let tabs = self.get_tabs().await?;
        
        if let Some(active_tab) = tabs.first() {
            Ok(active_tab.url.clone())
        } else {
            Err(anyhow::anyhow!("No active browser tabs found"))
        }
    }
    
    /// Detect DOM changes by comparing with previous state
    pub async fn detect_dom_changes(&self, previous_dom: Option<&DOMData>) -> Result<DOMChangeAnalysis> {
        let current_dom = self.extract_browser_context().await?;
        
        if let Some(prev) = previous_dom {
            Ok(DOMChangeAnalysis::compare(prev, &current_dom))
        } else {
            Ok(DOMChangeAnalysis::initial(&current_dom))
        }
    }
    
    /// Check if this is a specific browser type
    pub async fn detect_browser_type(&self) -> Result<String> {
        // Check if we can connect to Chrome DevTools
        if self.is_available().await {
            // Try to get version info to determine browser type
            let version_url = format!("http://localhost:{}/json/version", self.debugging_port);
            
            if let Ok(response) = self.client.get(&version_url).send().await {
                if let Ok(version_info) = response.json::<Value>().await {
                    if let Some(product) = version_info["Browser"].as_str() {
                        if product.contains("Chrome") {
                            return Ok("Chrome".to_string());
                        } else if product.contains("Chromium") {
                            return Ok("Chromium".to_string());
                        } else if product.contains("Edge") {
                            return Ok("Edge".to_string());
                        }
                    }
                }
            }
        }
        
        Ok("Unknown Chromium-based".to_string())
    }
}

impl Default for ChromiumBridge {
    fn default() -> Self {
        Self::new()
    }
}

/// Analysis of DOM changes between two states
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DOMChangeAnalysis {
    pub has_changes: bool,
    pub url_changed: bool,
    pub title_changed: bool,
    pub content_changes: ContentChanges,
    pub form_changes: FormChanges,
    pub navigation_changes: NavigationChanges,
    pub timestamp: std::time::SystemTime,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ContentChanges {
    pub text_similarity: f32,  // 0.0 = completely different, 1.0 = identical
    pub new_elements_detected: u32,
    pub removed_elements_detected: u32,
    pub scroll_changed: bool,
    pub viewport_changed: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FormChanges {
    pub new_forms: u32,
    pub removed_forms: u32,
    pub form_data_changed: bool,
    pub input_focus_changed: bool,
    pub new_input_values: u32,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct NavigationChanges {
    pub new_links: u32,
    pub removed_links: u32,
    pub button_changes: u32,
}

impl DOMChangeAnalysis {
    /// Create initial analysis for first DOM capture
    pub fn initial(dom: &DOMData) -> Self {
        Self {
            has_changes: true, // First capture always counts as change
            url_changed: false,
            title_changed: false,
            content_changes: ContentChanges {
                text_similarity: 1.0,
                new_elements_detected: dom.inputs.len() as u32 + dom.buttons.len() as u32,
                removed_elements_detected: 0,
                scroll_changed: false,
                viewport_changed: false,
            },
            form_changes: FormChanges {
                new_forms: dom.forms.len() as u32,
                removed_forms: 0,
                form_data_changed: false,
                input_focus_changed: false,
                new_input_values: 0,
            },
            navigation_changes: NavigationChanges {
                new_links: dom.links.len() as u32,
                removed_links: 0,
                button_changes: dom.buttons.len() as u32,
            },
            timestamp: std::time::SystemTime::now(),
        }
    }
    
    /// Compare two DOM states and analyze changes
    pub fn compare(previous: &DOMData, current: &DOMData) -> Self {
        let url_changed = previous.url != current.url;
        let title_changed = previous.title != current.title;
        
        // Calculate text similarity using simple word-based comparison
        let text_similarity = Self::calculate_text_similarity(&previous.visible_text, &current.visible_text);
        
        // Detect scroll changes
        let scroll_changed = previous.scroll_position != current.scroll_position;
        
        // Detect viewport changes
        let viewport_changed = previous.viewport_size != current.viewport_size;
        
        // Analyze form changes
        let form_count_diff = current.forms.len() as i32 - previous.forms.len() as i32;
        let input_focus_changed = Self::detect_input_focus_change(previous, current);
        let input_value_changes = Self::detect_input_value_changes(previous, current);
        
        // Analyze navigation changes
        let link_count_diff = current.links.len() as i32 - previous.links.len() as i32;
        let button_count_diff = current.buttons.len() as i32 - previous.buttons.len() as i32;
        
        let has_changes = url_changed || title_changed || text_similarity < 0.95 || 
                         scroll_changed || viewport_changed || form_count_diff != 0 ||
                         input_focus_changed || input_value_changes > 0 ||
                         link_count_diff != 0 || button_count_diff != 0;
        
        Self {
            has_changes,
            url_changed,
            title_changed,
            content_changes: ContentChanges {
                text_similarity,
                new_elements_detected: if form_count_diff > 0 { form_count_diff as u32 } else { 0 },
                removed_elements_detected: if form_count_diff < 0 { (-form_count_diff) as u32 } else { 0 },
                scroll_changed,
                viewport_changed,
            },
            form_changes: FormChanges {
                new_forms: if form_count_diff > 0 { form_count_diff as u32 } else { 0 },
                removed_forms: if form_count_diff < 0 { (-form_count_diff) as u32 } else { 0 },
                form_data_changed: form_count_diff != 0,
                input_focus_changed,
                new_input_values: input_value_changes,
            },
            navigation_changes: NavigationChanges {
                new_links: if link_count_diff > 0 { link_count_diff as u32 } else { 0 },
                removed_links: if link_count_diff < 0 { (-link_count_diff) as u32 } else { 0 },
                button_changes: button_count_diff.abs() as u32,
            },
            timestamp: std::time::SystemTime::now(),
        }
    }
    
    /// Calculate text similarity between two strings
    fn calculate_text_similarity(text1: &str, text2: &str) -> f32 {
        if text1 == text2 {
            return 1.0;
        }
        
        if text1.is_empty() && text2.is_empty() {
            return 1.0;
        }
        
        if text1.is_empty() || text2.is_empty() {
            return 0.0;
        }
        
        // Simple word-based similarity
        let words1: std::collections::HashSet<&str> = text1.split_whitespace().collect();
        let words2: std::collections::HashSet<&str> = text2.split_whitespace().collect();
        
        let intersection = words1.intersection(&words2).count();
        let union = words1.union(&words2).count();
        
        if union == 0 {
            1.0
        } else {
            intersection as f32 / union as f32
        }
    }
    
    /// Detect if input focus has changed
    fn detect_input_focus_change(previous: &DOMData, current: &DOMData) -> bool {
        let prev_focused = previous.inputs.iter().any(|input| input.is_focused);
        let curr_focused = current.inputs.iter().any(|input| input.is_focused);
        
        prev_focused != curr_focused
    }
    
    /// Detect changes in input values (by comparing value lengths)
    fn detect_input_value_changes(previous: &DOMData, current: &DOMData) -> u32 {
        let mut changes = 0;
        
        // Create maps by input name for comparison
        let prev_inputs: HashMap<String, &InputData> = previous.inputs.iter()
            .filter_map(|input| input.name.as_ref().map(|name| (name.clone(), input)))
            .collect();
        
        let curr_inputs: HashMap<String, &InputData> = current.inputs.iter()
            .filter_map(|input| input.name.as_ref().map(|name| (name.clone(), input)))
            .collect();
        
        for (name, curr_input) in curr_inputs {
            if let Some(prev_input) = prev_inputs.get(&name) {
                if prev_input.value_length != curr_input.value_length {
                    changes += 1;
                }
            }
        }
        
        changes
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    
    #[test]
    fn test_chromium_bridge_creation() {
        let bridge = ChromiumBridge::new();
        assert_eq!(bridge.debugging_port, 9222);
    }
    
    #[test]
    fn test_custom_debugging_port() {
        let bridge = ChromiumBridge::new().with_debugging_port(9223);
        assert_eq!(bridge.debugging_port, 9223);
    }
    
    #[tokio::test]
    async fn test_availability_check() {
        let bridge = ChromiumBridge::new();
        // This will fail if Chrome isn't running with --remote-debugging-port=9222
        let _is_available = bridge.is_available().await;
        // We can't assert true/false as it depends on Chrome being available
    }
    
    #[tokio::test]
    async fn test_get_tabs_no_chrome() {
        let bridge = ChromiumBridge::new().with_debugging_port(9999); // Unlikely port
        let result = bridge.get_tabs().await;
        assert!(result.is_err());
    }
}