//! Enhanced decline handling for tab completion
//!
//! This module provides context tracking and enrichment for when predictions are declined,
//! allowing for better retry predictions that incorporate:
//! - What the user was actually typing (chars typed after prediction)
//! - The declined prediction (so we don't repeat it)
//! - Current recommended actions (user's likely intent)

use serde::{Deserialize, Serialize};

/// Context captured when a prediction is declined
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DeclineContext {
    /// The prediction that was declined
    pub declined_prediction: String,

    /// Full text buffer at time of decline
    pub typed_text: String,

    /// Characters typed AFTER prediction was shown (reveals user's intent)
    pub chars_after_prediction: String,

    /// How long the prediction was visible before decline (ms)
    pub time_to_decline_ms: u64,

    /// Retry attempt number (0 = first prediction, 1 = first retry after decline, etc.)
    pub retry_count: u8,

    /// Timestamp when decline occurred
    pub timestamp: u64,
}

impl DeclineContext {
    /// Create a new decline context
    pub fn new(
        declined_prediction: String,
        typed_text: String,
        chars_after_prediction: String,
        time_to_decline_ms: u64,
    ) -> Self {
        Self {
            declined_prediction,
            typed_text,
            chars_after_prediction,
            time_to_decline_ms,
            retry_count: 0,
            timestamp: std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap()
                .as_secs(),
        }
    }

    /// Create a retry context (increments retry count)
    pub fn with_retry(&self) -> Self {
        Self {
            retry_count: self.retry_count + 1,
            ..self.clone()
        }
    }

    /// Check if we should stop retrying (max 2 retries)
    pub fn should_stop_retrying(&self) -> bool {
        self.retry_count >= 2
    }
}

/// Summary of a recommended action for inclusion in prompts
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ActionSummary {
    /// Action title/name
    pub action_name: String,
    /// Action description/plan
    pub action_plan: String,
}

impl ActionSummary {
    pub fn new(action_name: String, action_plan: String) -> Self {
        Self {
            action_name,
            action_plan,
        }
    }
}

/// Enriched context for prediction that includes decline history and recommended actions
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct EnrichedPredictionContext {
    /// Current recommended actions from ActionsStore
    pub recommended_actions: Vec<ActionSummary>,

    /// Decline history for this session (if retrying)
    pub decline_context: Option<DeclineContext>,

    /// Recent typing pattern
    pub recent_typing: String,

    /// Current app name
    pub app_name: String,
}

impl EnrichedPredictionContext {
    pub fn new(app_name: String) -> Self {
        Self {
            recommended_actions: Vec::new(),
            decline_context: None,
            recent_typing: String::new(),
            app_name,
        }
    }

    /// Add recommended actions
    pub fn with_actions(mut self, actions: Vec<ActionSummary>) -> Self {
        self.recommended_actions = actions;
        self
    }

    /// Add decline context
    pub fn with_decline(mut self, decline: DeclineContext) -> Self {
        self.recent_typing = decline.typed_text.clone();
        self.decline_context = Some(decline);
        self
    }

    /// Add recent typing
    pub fn with_typing(mut self, typing: String) -> Self {
        self.recent_typing = typing;
        self
    }

    /// Check if this is a retry (has decline context)
    pub fn is_retry(&self) -> bool {
        self.decline_context.is_some()
    }

    /// Get the chars typed after the declined prediction (user's intent)
    pub fn get_user_intent_chars(&self) -> Option<&str> {
        self.decline_context.as_ref().map(|d| d.chars_after_prediction.as_str())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_decline_context_creation() {
        let ctx = DeclineContext::new(
            "function()".to_string(),
            "const f = fu".to_string(),
            "nction".to_string(),
            250,
        );

        assert_eq!(ctx.declined_prediction, "function()");
        assert_eq!(ctx.chars_after_prediction, "nction");
        assert_eq!(ctx.retry_count, 0);
        assert!(!ctx.should_stop_retrying());
    }

    #[test]
    fn test_retry_count() {
        let ctx = DeclineContext::new(
            "test".to_string(),
            "te".to_string(),
            "st".to_string(),
            100,
        );

        let retry1 = ctx.with_retry();
        assert_eq!(retry1.retry_count, 1);
        assert!(!retry1.should_stop_retrying());

        let retry2 = retry1.with_retry();
        assert_eq!(retry2.retry_count, 2);
        assert!(retry2.should_stop_retrying());
    }

    #[test]
    fn test_enriched_context() {
        let actions = vec![
            ActionSummary::new("Review PR".to_string(), "Review pull request #123".to_string()),
        ];

        let decline = DeclineContext::new(
            "old prediction".to_string(),
            "typed text".to_string(),
            "new chars".to_string(),
            200,
        );

        let enriched = EnrichedPredictionContext::new("VSCode".to_string())
            .with_actions(actions)
            .with_decline(decline);

        assert!(enriched.is_retry());
        assert_eq!(enriched.recommended_actions.len(), 1);
        assert_eq!(enriched.get_user_intent_chars(), Some("new chars"));
    }
}
