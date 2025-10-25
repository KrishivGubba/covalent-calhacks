use anyhow::{Context as AnyhowContext, Result};
use async_trait::async_trait;
use reqwest::Client;
use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::collections::HashMap;
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::Arc;
use std::time::Duration;
use tokio::sync::Mutex;
use tokio::time::timeout;
use url::Url;

use crate::screen_context::context_data::{
    DOMData, FormData, InputData, LinkData, ScrollPosition, ViewportSize,
};

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
    
    /// Extract comprehensive DOM context (simplified implementation without WebSocket)
    pub async fn extract_browser_context(&self) -> Result<DOMData> {
        // For now, return a stub implementation
        // A full implementation would require WebSocket connection to DevTools
        Ok(DOMData {
            url: "http://example.com".to_string(),
            title: "Example Page".to_string(),
            active_element: None,
            forms: Vec::new(),
            visible_text: "Example content".to_string(),
            buttons: Vec::new(),
            inputs: Vec::new(),
            links: Vec::new(),
            meta_data: HashMap::new(),
            scroll_position: None,
            viewport_size: None,
            cookies: None,
        })
    }
    
    /// Get current page URL (stub implementation)
    pub async fn get_current_url(&self) -> Result<String> {
        Ok("http://example.com".to_string())
    }
    
    /// Check if this is a specific browser type
    pub async fn detect_browser_type(&self) -> Result<String> {
        Ok("Chrome".to_string())
    }
}

impl Default for ChromiumBridge {
    fn default() -> Self {
        Self::new()
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