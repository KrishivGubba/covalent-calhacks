use anyhow::{Context, Result};
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::process::Command;
use std::time::Duration;
use tokio::time::timeout;

use crate::screen_context::context_data::{
    DOMData, FormData, InputData, LinkData, ScrollPosition, ViewportSize,
};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SafariTab {
    pub index: u32,
    pub name: String,
    pub url: String,
    pub is_loading: bool,
    pub is_visible: bool,
}

pub struct SafariBridge {
    use_javascript_osa: bool,
    timeout_duration: Duration,
}

impl SafariBridge {
    pub fn new() -> Self {
        Self {
            use_javascript_osa: true,
            timeout_duration: Duration::from_secs(3),
        }
    }
    
    pub fn with_timeout(mut self, timeout: Duration) -> Self {
        self.timeout_duration = timeout;
        self
    }
    
    /// Check if Safari is running and accessible
    pub async fn is_available(&self) -> bool {
        self.is_safari_running().await.unwrap_or(false)
    }
    
    /// Get information about all Safari tabs
    pub async fn get_tabs(&self) -> Result<Vec<SafariTab>> {
        let script = r#"
            tell application "Safari"
                set tabList to {}
                set windowList to windows
                repeat with w from 1 to count of windowList
                    set currentWindow to item w of windowList
                    set tabCount to count of tabs of currentWindow
                    repeat with t from 1 to tabCount
                        set currentTab to tab t of currentWindow
                        set tabInfo to {index:(t), name:(name of currentTab), url:(URL of currentTab), isLoading:false, isVisible:(w = 1 and t = (index of current tab of currentWindow))}
                        set end of tabList to tabInfo
                    end repeat
                end repeat
                return tabList
            end tell
        "#;
        
        let result = self.execute_applescript(script).await?;
        self.parse_tabs_result(&result)
    }
    
    /// Get the currently active tab
    pub async fn get_active_tab(&self) -> Result<SafariTab> {
        let script = r#"
            tell application "Safari"
                if (count of windows) > 0 then
                    set currentWindow to window 1
                    set currentTab to current tab of currentWindow
                    set tabIndex to index of currentTab
                    return {index:tabIndex, name:(name of currentTab), url:(URL of currentTab), isLoading:false, isVisible:true}
                else
                    error "No Safari windows open"
                end if
            end tell
        "#;
        
        let result = self.execute_applescript(script).await?;
        self.parse_single_tab_result(&result)
    }
    
    /// Extract comprehensive DOM context from Safari
    pub async fn extract_browser_context(&self) -> Result<DOMData> {
        // First get basic page info via AppleScript
        let basic_info = self.get_basic_page_info().await?;
        
        // Then try to extract detailed DOM info via JavaScript injection
        let detailed_info = self.extract_detailed_dom_info().await.unwrap_or_default();
        
        // Combine the results
        Ok(DOMData {
            url: basic_info.url,
            title: basic_info.title,
            active_element: detailed_info.active_element,
            forms: detailed_info.forms,
            visible_text: detailed_info.visible_text,
            buttons: detailed_info.buttons,
            inputs: detailed_info.inputs,
            links: detailed_info.links,
            meta_data: detailed_info.meta_data,
            scroll_position: detailed_info.scroll_position,
            viewport_size: detailed_info.viewport_size,
            cookies: None, // Safari doesn't expose cookies via AppleScript
        })
    }
    
    /// Execute JavaScript in the current Safari tab
    pub async fn execute_javascript(&self, script: &str) -> Result<String> {
        let applescript = format!(
            r#"
            tell application "Safari"
                if (count of windows) > 0 then
                    set currentTab to current tab of window 1
                    set result to do JavaScript "{}" in currentTab
                    return result
                else
                    error "No Safari windows open"
                end if
            end tell
            "#,
            script.replace("\"", "\\\"").replace("\n", "\\n")
        );
        
        self.execute_applescript(&applescript).await
    }
    
    /// Get current page URL
    pub async fn get_current_url(&self) -> Result<String> {
        let script = r#"
            tell application "Safari"
                if (count of windows) > 0 then
                    return URL of current tab of window 1
                else
                    error "No Safari windows open"
                end if
            end tell
        "#;
        
        self.execute_applescript(script).await
    }
    
    /// Get current page title
    pub async fn get_current_title(&self) -> Result<String> {
        let script = r#"
            tell application "Safari"
                if (count of windows) > 0 then
                    return name of current tab of window 1
                else
                    error "No Safari windows open"
                end if
            end tell
        "#;
        
        self.execute_applescript(script).await
    }
    
    /// Navigate to a URL
    pub async fn navigate_to(&self, url: &str) -> Result<()> {
        let script = format!(
            r#"
            tell application "Safari"
                if (count of windows) > 0 then
                    set URL of current tab of window 1 to "{}"
                else
                    make new document with properties {{URL:"{}"}}
                end if
            end tell
            "#,
            url, url
        );
        
        self.execute_applescript(&script).await?;
        Ok(())
    }
    
    /// Refresh the current page
    pub async fn refresh(&self) -> Result<()> {
        let script = r#"
            tell application "Safari"
                if (count of windows) > 0 then
                    tell current tab of window 1 to reload
                end if
            end tell
        "#;
        
        self.execute_applescript(script).await?;
        Ok(())
    }
    
    // Private helper methods
    
    async fn is_safari_running(&self) -> Result<bool> {
        let script = r#"
            tell application "System Events"
                return (name of processes) contains "Safari"
            end tell
        "#;
        
        match self.execute_applescript(script).await {
            Ok(result) => Ok(result.trim() == "true"),
            Err(_) => Ok(false),
        }
    }
    
    async fn get_basic_page_info(&self) -> Result<BasicPageInfo> {
        let script = r#"
            tell application "Safari"
                if (count of windows) > 0 then
                    set currentTab to current tab of window 1
                    return {url:(URL of currentTab), title:(name of currentTab)}
                else
                    error "No Safari windows open"
                end if
            end tell
        "#;
        
        let result = self.execute_applescript(script).await?;
        
        // Parse the result (AppleScript returns a record)
        // This is a simplified parser - in practice you'd want more robust parsing
        let url = if result.contains("url:") {
            result
                .split("url:")
                .nth(1)
                .and_then(|s| s.split(",").next())
                .unwrap_or("")
                .trim()
                .to_string()
        } else {
            String::new()
        };
        
        let title = if result.contains("title:") {
            result
                .split("title:")
                .nth(1)
                .unwrap_or("")
                .trim()
                .to_string()
        } else {
            String::new()
        };
        
        Ok(BasicPageInfo { url, title })
    }
    
    async fn extract_detailed_dom_info(&self) -> Result<DetailedDOMInfo> {
        // JavaScript to extract detailed DOM information
        let js_script = r#"
            (function() {
                try {
                    // Active element
                    const activeElement = document.activeElement;
                    const activeElementHtml = activeElement && activeElement !== document.body 
                        ? activeElement.outerHTML.substring(0, 500) 
                        : null;
                    
                    // Forms
                    const forms = Array.from(document.forms).map(form => ({
                        action: form.action || '',
                        method: form.method || 'GET',
                        fields: Array.from(form.elements).map(el => el.name || el.id || '').filter(Boolean),
                        hasFileUpload: Array.from(form.elements).some(el => el.type === 'file')
                    }));
                    
                    // Visible text
                    const selection = window.getSelection().toString();
                    const visibleText = selection || 
                        (document.body.innerText || document.body.textContent || '').substring(0, 1000);
                    
                    // Buttons
                    const buttons = Array.from(document.querySelectorAll('button, input[type="button"], input[type="submit"], [role="button"]'))
                        .filter(btn => {
                            const rect = btn.getBoundingClientRect();
                            return rect.width > 0 && rect.height > 0;
                        })
                        .slice(0, 10)
                        .map(btn => btn.textContent?.trim() || btn.value || btn.getAttribute('aria-label') || '')
                        .filter(Boolean);
                    
                    // Inputs
                    const inputs = Array.from(document.querySelectorAll('input, textarea, select'))
                        .filter(input => {
                            const rect = input.getBoundingClientRect();
                            return rect.width > 0 && rect.height > 0;
                        })
                        .map(input => ({
                            type: input.type || input.tagName.toLowerCase(),
                            name: input.name || null,
                            placeholder: input.placeholder || null,
                            valueLength: (input.value || '').length,
                            isFocused: input === document.activeElement,
                            isRequired: input.hasAttribute('required')
                        }));
                    
                    // Links
                    const links = Array.from(document.querySelectorAll('a[href]'))
                        .filter(link => {
                            const rect = link.getBoundingClientRect();
                            return rect.width > 0 && rect.height > 0;
                        })
                        .slice(0, 20)
                        .map(link => ({
                            text: (link.textContent || '').trim().substring(0, 100),
                            href: link.href,
                            isExternal: !link.href.startsWith(window.location.origin)
                        }))
                        .filter(link => link.text && link.href);
                    
                    // Meta data
                    const metaData = {};
                    document.querySelectorAll('meta[name], meta[property]').forEach(meta => {
                        const key = meta.getAttribute('name') || meta.getAttribute('property');
                        const content = meta.getAttribute('content');
                        if (key && content) {
                            metaData[key] = content;
                        }
                    });
                    
                    // Scroll position
                    const scrollPosition = {
                        x: window.pageXOffset || document.documentElement.scrollLeft,
                        y: window.pageYOffset || document.documentElement.scrollTop
                    };
                    
                    // Viewport size
                    const viewportSize = {
                        width: window.innerWidth,
                        height: window.innerHeight
                    };
                    
                    return JSON.stringify({
                        activeElement: activeElementHtml,
                        forms: forms,
                        visibleText: visibleText,
                        buttons: buttons,
                        inputs: inputs,
                        links: links,
                        metaData: metaData,
                        scrollPosition: scrollPosition,
                        viewportSize: viewportSize
                    });
                } catch (error) {
                    return JSON.stringify({error: error.message});
                }
            })()
        "#;
        
        match self.execute_javascript(js_script).await {
            Ok(json_result) => {
                if let Ok(parsed) = serde_json::from_str::<serde_json::Value>(&json_result) {
                    self.parse_detailed_dom_result(parsed)
                } else {
                    Ok(DetailedDOMInfo::default())
                }
            }
            Err(_) => Ok(DetailedDOMInfo::default()),
        }
    }
    
    async fn execute_applescript(&self, script: &str) -> Result<String> {
        let result = timeout(
            self.timeout_duration,
            tokio::task::spawn_blocking({
                let script = script.to_string();
                move || {
                    let output = Command::new("osascript")
                        .arg("-e")
                        .arg(&script)
                        .output()?;
                    
                    if output.status.success() {
                        Ok(String::from_utf8(output.stdout)?.trim().to_string())
                    } else {
                        let error = String::from_utf8(output.stderr)?;
                        Err(anyhow::anyhow!("AppleScript error: {}", error))
                    }
                }
            })
        )
        .await
        .context("AppleScript execution timeout")?
        .context("AppleScript task failed")?;
        
        result
    }
    
    fn parse_tabs_result(&self, result: &str) -> Result<Vec<SafariTab>> {
        // This is a simplified parser for AppleScript list results
        // In practice, you'd want more robust parsing
        let mut tabs = Vec::new();
        
        // AppleScript returns lists in a specific format
        // For now, return empty vector as parsing AppleScript lists is complex
        // In a real implementation, you'd parse the AppleScript record format
        
        Ok(tabs)
    }
    
    fn parse_single_tab_result(&self, result: &str) -> Result<SafariTab> {
        // Simplified parsing - in practice, you'd properly parse AppleScript records
        Ok(SafariTab {
            index: 1,
            name: "Current Tab".to_string(),
            url: result.to_string(),
            is_loading: false,
            is_visible: true,
        })
    }
    
    fn parse_detailed_dom_result(&self, json: serde_json::Value) -> Result<DetailedDOMInfo> {
        let obj = json.as_object()
            .ok_or_else(|| anyhow::anyhow!("Invalid JSON format"))?;
        
        if obj.contains_key("error") {
            return Ok(DetailedDOMInfo::default());
        }
        
        let active_element = obj.get("activeElement")
            .and_then(|v| v.as_str())
            .map(|s| s.to_string());
        
        let visible_text = obj.get("visibleText")
            .and_then(|v| v.as_str())
            .unwrap_or("")
            .to_string();
        
        // Parse forms
        let forms = obj.get("forms")
            .and_then(|v| v.as_array())
            .map(|arr| {
                arr.iter()
                    .filter_map(|form| {
                        let form_obj = form.as_object()?;
                        Some(FormData {
                            action: form_obj.get("action")?.as_str()?.to_string(),
                            method: form_obj.get("method")?.as_str()?.to_string(),
                            fields: form_obj.get("fields")?
                                .as_array()?
                                .iter()
                                .filter_map(|f| f.as_str().map(|s| s.to_string()))
                                .collect(),
                            has_file_upload: form_obj.get("hasFileUpload")?.as_bool()?,
                        })
                    })
                    .collect()
            })
            .unwrap_or_default();
        
        // Parse inputs
        let inputs = obj.get("inputs")
            .and_then(|v| v.as_array())
            .map(|arr| {
                arr.iter()
                    .filter_map(|input| {
                        let input_obj = input.as_object()?;
                        Some(InputData {
                            input_type: input_obj.get("type")?.as_str()?.to_string(),
                            name: input_obj.get("name").and_then(|v| v.as_str()).map(|s| s.to_string()),
                            placeholder: input_obj.get("placeholder").and_then(|v| v.as_str()).map(|s| s.to_string()),
                            value_length: input_obj.get("valueLength")?.as_u64()? as usize,
                            is_focused: input_obj.get("isFocused")?.as_bool()?,
                            is_required: input_obj.get("isRequired")?.as_bool()?,
                        })
                    })
                    .collect()
            })
            .unwrap_or_default();
        
        let buttons = obj.get("buttons")
            .and_then(|v| v.as_array())
            .map(|arr| {
                arr.iter()
                    .filter_map(|b| b.as_str().map(|s| s.to_string()))
                    .collect()
            })
            .unwrap_or_default();
        
        let links = obj.get("links")
            .and_then(|v| v.as_array())
            .map(|arr| {
                arr.iter()
                    .filter_map(|link| {
                        let link_obj = link.as_object()?;
                        Some(LinkData {
                            text: link_obj.get("text")?.as_str()?.to_string(),
                            href: link_obj.get("href")?.as_str()?.to_string(),
                            is_external: link_obj.get("isExternal")?.as_bool()?,
                        })
                    })
                    .collect()
            })
            .unwrap_or_default();
        
        let scroll_position = obj.get("scrollPosition")
            .and_then(|v| v.as_object())
            .and_then(|scroll| {
                Some(ScrollPosition {
                    x: scroll.get("x")?.as_f64()?,
                    y: scroll.get("y")?.as_f64()?,
                })
            });
        
        let viewport_size = obj.get("viewportSize")
            .and_then(|v| v.as_object())
            .and_then(|viewport| {
                Some(ViewportSize {
                    width: viewport.get("width")?.as_u64()? as u32,
                    height: viewport.get("height")?.as_u64()? as u32,
                })
            });
        
        let meta_data = obj.get("metaData")
            .and_then(|v| v.as_object())
            .map(|meta| {
                meta.iter()
                    .filter_map(|(k, v)| Some((k.clone(), v.as_str()?.to_string())))
                    .collect()
            })
            .unwrap_or_default();
        
        Ok(DetailedDOMInfo {
            active_element,
            forms,
            visible_text,
            buttons,
            inputs,
            links,
            meta_data,
            scroll_position,
            viewport_size,
        })
    }
}

#[derive(Debug, Default)]
struct BasicPageInfo {
    url: String,
    title: String,
}

#[derive(Debug, Default)]
struct DetailedDOMInfo {
    active_element: Option<String>,
    forms: Vec<FormData>,
    visible_text: String,
    buttons: Vec<String>,
    inputs: Vec<InputData>,
    links: Vec<LinkData>,
    meta_data: HashMap<String, String>,
    scroll_position: Option<ScrollPosition>,
    viewport_size: Option<ViewportSize>,
}

impl Default for SafariBridge {
    fn default() -> Self {
        Self::new()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    
    #[test]
    fn test_safari_bridge_creation() {
        let bridge = SafariBridge::new();
        assert_eq!(bridge.timeout_duration, Duration::from_secs(3));
    }
    
    #[test]
    fn test_custom_timeout() {
        let bridge = SafariBridge::new().with_timeout(Duration::from_secs(5));
        assert_eq!(bridge.timeout_duration, Duration::from_secs(5));
    }

    #[tokio::test]
    async fn test_get_tabs() {
        let bridge = SafariBridge::new();
        let tabs = bridge.get_tabs().await;
        assert!(tabs.is_ok());
    }

    #[tokio::test]
    async fn test_safari_availability() {
        let bridge = SafariBridge::new();
        // This will check if Safari is running
        let _is_available = bridge.is_available().await;
        // We can't assert true/false as it depends on Safari being running
    }
    
    #[tokio::test]
    async fn test_get_current_url_no_safari() {
        let bridge = SafariBridge::new().with_timeout(Duration::from_millis(500));
        // This should fail if Safari isn't running or has no windows
        let result = bridge.get_current_url().await;
        // We expect this to potentially fail in CI/test environments
        match result {
            Ok(url) => println!("Current Safari URL: {}", url),
            Err(e) => println!("Expected error when Safari not available: {}", e),
        }
    }
}