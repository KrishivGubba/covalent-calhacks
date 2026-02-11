use std::io::{self, Write};

/// ANSI-based terminal ghost text display
/// Works in most terminals but has limitations (can conflict with terminal rendering)
pub struct TerminalDisplay;

impl TerminalDisplay {
    /// Show ghost text at current cursor position
    /// Uses ANSI escape sequences for dimmed text
    pub fn show_ghost_text(text: &str) -> io::Result<()> {
        let stdout = io::stdout();
        let mut handle = stdout.lock();

        // Save cursor position
        write!(handle, "\x1b[s")?;

        // Print dimmed text (ANSI dim mode)
        write!(handle, "\x1b[2m{}\x1b[0m", text)?;

        // Restore cursor position
        write!(handle, "\x1b[u")?;

        handle.flush()?;
        Ok(())
    }

    /// Clear ghost text (move to where it was and overwrite with spaces)
    pub fn clear_ghost_text(length: usize) -> io::Result<()> {
        let stdout = io::stdout();
        let mut handle = stdout.lock();

        // Save cursor position
        write!(handle, "\x1b[s")?;

        // Overwrite with spaces
        write!(handle, "{}", " ".repeat(length))?;

        // Restore cursor position
        write!(handle, "\x1b[u")?;

        handle.flush()?;
        Ok(())
    }

    /// Show ghost text with color (gray/dim)
    /// More visible than just dimmed text
    pub fn show_ghost_text_colored(text: &str) -> io::Result<()> {
        let stdout = io::stdout();
        let mut handle = stdout.lock();

        // Save cursor position
        write!(handle, "\x1b[s")?;

        // Print in gray color (ANSI color 8 = bright black/gray)
        write!(handle, "\x1b[90m{}\x1b[0m", text)?;

        // Restore cursor position
        write!(handle, "\x1b[u")?;

        handle.flush()?;
        Ok(())
    }

    /// Show inline suggestion (like GitHub Copilot style)
    /// Displays prediction in dim gray at the current line
    pub fn show_inline_suggestion(prediction: &str, cache_level: &str, latency_ms: u128) -> io::Result<()> {
        let stdout = io::stdout();
        let mut handle = stdout.lock();

        // Truncate prediction to reasonable length
        let display_text = if prediction.chars().count() > 60 {
            let truncated: String = prediction.chars().take(57).collect();
            format!("{}...", truncated)
        } else {
            prediction.to_string()
        };

        // Save cursor position
        write!(handle, "\x1b[s")?;

        // Print prediction in gray with metadata
        write!(
            handle,
            "\x1b[90m{} \x1b[2m[{} {}ms]\x1b[0m",
            display_text,
            cache_level,
            latency_ms
        )?;

        // Restore cursor position
        write!(handle, "\x1b[u")?;

        handle.flush()?;
        Ok(())
    }

    /// Show prediction as status line at bottom of terminal
    /// Requires terminal with status line support
    pub fn show_as_status_line(prediction: &str, cache_level: &str) -> io::Result<()> {
        let stdout = io::stdout();
        let mut handle = stdout.lock();

        // Save cursor position
        write!(handle, "\x1b[s")?;

        // Move to bottom of screen (assuming 24 lines, adjust as needed)
        write!(handle, "\x1b[24;0H")?;

        // Clear line and show prediction
        write!(handle, "\x1b[2K")?;
        let status_preview: String = prediction.chars().take(80).collect();
        write!(
            handle,
            "\x1b[7m Suggestion [{}]: {} \x1b[0m",
            cache_level,
            status_preview
        )?;

        // Restore cursor position
        write!(handle, "\x1b[u")?;

        handle.flush()?;
        Ok(())
    }

    /// Detect if we're in iTerm2 (for advanced features)
    pub fn is_iterm2() -> bool {
        std::env::var("TERM_PROGRAM")
            .map(|term| term == "iTerm.app")
            .unwrap_or(false)
    }

    /// Show ghost text using iTerm2-specific features if available
    #[allow(dead_code)]
    pub fn show_iterm2_ghost_text(text: &str) -> io::Result<()> {
        if !Self::is_iterm2() {
            return Self::show_ghost_text_colored(text);
        }

        let stdout = io::stdout();
        let mut handle = stdout.lock();

        // iTerm2 PreEdit mode (experimental)
        write!(handle, "\x1b]1337;PreEdit={}\x07", text)?;

        handle.flush()?;
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_terminal_display_creation() {
        // Just verify the struct exists
        let _display = TerminalDisplay;
    }

    #[test]
    fn test_is_iterm2() {
        // This will return false in test environment
        let result = TerminalDisplay::is_iterm2();
        assert!(!result || result); // Always passes, just testing it doesn't panic
    }
}
