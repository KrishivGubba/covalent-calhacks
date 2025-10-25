pub struct WorkflowDetector {
    pattern_buffer: CircularBuffer<IntentAnalysis>,
    known_patterns: HashMap<String, WorkflowPattern>,
}

impl WorkflowDetector {
    pub fn detect_workflow(&mut self, 
                          current: &IntentAnalysis) -> Option<Workflow> {
        self.pattern_buffer.push(current.clone());
        
        // Look for patterns in recent actions
        let recent_actions = self.pattern_buffer.last_n(10);
        
        // Check for repetitive patterns
        if let Some(pattern) = self.find_repetition(&recent_actions) {
            return Some(Workflow::Repetitive(pattern));
        }
        
        // Check for known workflow stages
        for (name, pattern) in &self.known_patterns {
            if pattern.matches(&recent_actions) {
                return Some(Workflow::Known {
                    name: name.clone(),
                    stage: pattern.current_stage(&recent_actions),
                    next_likely_action: pattern.predict_next(&recent_actions),
                });
            }
        }
        
        // Detect form filling patterns
        if self.is_form_workflow(&recent_actions) {
            return Some(Workflow::FormFilling {
                fields_completed: self.extract_completed_fields(&recent_actions),
                fields_remaining: self.predict_remaining_fields(&recent_actions),
            });
        }
        
        None
    }
}