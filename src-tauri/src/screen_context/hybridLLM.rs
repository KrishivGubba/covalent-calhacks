// Use a smaller model for quick analysis, Claude for complex cases
pub struct HybridLLM {
    local_model: Option<Llama2>,  // For fast, simple analysis
    claude_client: ClaudeClient,   // For complex analysis
}

impl HybridLLM {
    pub async fn analyze(&self, context: &RawContext) -> IntentAnalysis {
        // Quick local analysis first
        if let Some(local) = &self.local_model {
            let quick_analysis = local.analyze(context).await;
            
            // If confident enough, use it
            if quick_analysis.confidence > 0.8 {
                return quick_analysis;
            }
        }
        
        // Fall back to Claude for complex cases
        self.claude_client.analyze_detailed(context).await
    }
}