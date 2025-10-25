pub struct IntentAnalyzer {
    llm_client: ClaudeClient,  
    context_history: Vec<IntentAnalysis>,
}

impl IntentAnalyzer {
    pub async fn analyze(&mut self, raw_context: RawContext) -> IntentAnalysis {
        let prompt = self.build_analysis_prompt(&raw_context);
        
        // Use structured output from Claude
        let analysis = self.llm_client
            .complete_with_json::<IntentAnalysisResponse>(&prompt)
            .await?;
            
        // Post-process and validate
        self.validate_and_enrich(analysis, raw_context).await
    }
    
    fn build_analysis_prompt(&self, context: &RawContext) -> String {
        format!(r#"
        Analyze the user's current activity and intent based on this context:
        
        App: {} ({})
        Window: {}
        
        {}
        
        {}
        
        Previous context: {}
        
        Generate a JSON response with:
        1. action_description: A 200-300 word description capturing ALL key details about what the user is doing, their intent, and the context. This needs to be detailed enough for semantic search to work well.
        
        2. context_type: Select the most appropriate from: Coding, Writing, Researching, Designing, DataAnalysis, Meeting, EmailComposing, Messaging, Reading, Shopping, Learning, FileManagement, Configuration, Multitasking
        
        3. delta_analysis: Analyze what changed and what the user is trying to accomplish at a higher level. If they're filling forms, identify the workflow. If coding, identify the feature being built.
        
        Focus on understanding patterns and workflows, not just atomic actions.
        "#,
            context.app_info.name,
            context.app_info.bundle_id,
            context.app_info.window_title,
            self.format_dom_context(&context.dom_data),
            self.format_ocr_context(&context.ocr_data),
            self.format_previous_context(),
        )
    }
}