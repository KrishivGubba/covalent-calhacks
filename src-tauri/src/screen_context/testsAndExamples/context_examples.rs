// Examples demonstrating the enhanced ContextType system

use super::context_type::{
    ContextType, DevelopmentType, CommunicationType, ResearchType,
    CreativeType, DataWorkType, AdministrationType, ContextHierarchy,
};

#[allow(dead_code)]
pub fn example_bundle_id_detection() {
    // Example 1: Detecting context from VS Code
    let (context, confidence) = ContextType::from_app_bundle_id("com.microsoft.VSCode");
    println!("Bundle ID: com.microsoft.VSCode");
    println!("Context: {}", context);
    println!("Confidence: {:.2}%", confidence * 100.0);
    println!("Tags: {:?}", context.to_embedding_tags());
    println!();

    // Example 2: Detecting context from Zoom
    let (context, confidence) = ContextType::from_app_bundle_id("us.zoom.xos");
    println!("Bundle ID: us.zoom.xos");
    println!("Context: {}", context);
    println!("Confidence: {:.2}%", confidence * 100.0);
    println!("Category: {}", context.category_name());
    println!("Subcategory: {}", context.subcategory_name());
    println!();

    // Example 3: Detecting context from Figma
    let (context, confidence) = ContextType::from_app_bundle_id("com.figma.Desktop");
    println!("Bundle ID: com.figma.Desktop");
    println!("Context: {}", context);
    println!("Confidence: {:.2}%", confidence * 100.0);
    println!();
}

#[allow(dead_code)]
pub fn example_window_title_detection() {
    // Example 1: Detecting frontend development from window title
    let (context, confidence) = ContextType::from_window_title(
        "App.tsx - my-project - Visual Studio Code",
        Some("com.microsoft.VSCode")
    );
    println!("Window: App.tsx - my-project - Visual Studio Code");
    println!("Context: {}", context);
    println!("Confidence: {:.2}%", confidence * 100.0);
    println!();

    // Example 2: Detecting code review activity
    let (context, confidence) = ContextType::from_window_title(
        "Pull Request #42: Add user authentication - GitHub",
        None
    );
    println!("Window: Pull Request #42: Add user authentication - GitHub");
    println!("Context: {}", context);
    println!("Confidence: {:.2}%", confidence * 100.0);
    println!();

    // Example 3: Detecting data work
    let (context, confidence) = ContextType::from_window_title(
        "Q3 Sales Dashboard - Tableau",
        None
    );
    println!("Window: Q3 Sales Dashboard - Tableau");
    println!("Context: {}", context);
    println!("Confidence: {:.2}%", confidence * 100.0);
    println!();
}

#[allow(dead_code)]
pub fn example_context_hierarchy() {
    // Example: Creating a context hierarchy for frontend development
    let context = ContextType::Development(DevelopmentType::Frontend);
    let hierarchy = ContextHierarchy::new(context.clone());
    
    println!("Current Context: {}", context);
    println!("Category: {}", context.category_name());
    println!("Subcategory: {}", context.subcategory_name());
    println!("Hierarchy Depth: {}", hierarchy.depth());
    println!("Path: {:?}", hierarchy.path());
    println!();
    
    println!("Related Contexts:");
    for related in &hierarchy.related_contexts {
        println!("  - {}", related);
    }
    println!();
    
    println!("All Possible Development Subcategories:");
    for child in &hierarchy.children {
        println!("  - {}", child);
    }
    println!();
}

#[allow(dead_code)]
pub fn example_embedding_tags() {
    // Example: Getting tags for different context types
    let contexts = vec![
        ContextType::Development(DevelopmentType::Backend),
        ContextType::Communication(CommunicationType::VideoMeeting),
        ContextType::Research(ResearchType::APIDocumentation),
        ContextType::Creative(CreativeType::UIDesign),
        ContextType::DataWork(DataWorkType::Spreadsheet),
        ContextType::Administration(AdministrationType::TaskManagement),
    ];
    
    for context in contexts {
        println!("Context: {}", context.category_name());
        println!("Embedding Tags: {:?}", context.to_embedding_tags());
        println!();
    }
}

#[allow(dead_code)]
pub fn example_multitasking_context() {
    // Example: Handling multitasking scenarios
    let contexts = vec![
        ContextType::Development(DevelopmentType::Frontend),
        ContextType::Research(ResearchType::APIDocumentation),
        ContextType::Communication(CommunicationType::SlackDiscussion),
    ];
    
    let multitasking = ContextType::Multitasking(contexts.clone());
    
    println!("Multitasking Context: {}", multitasking);
    println!("Overall Confidence: {:.2}%", multitasking.confidence_score() * 100.0);
    println!();
    
    println!("All Tags (Combined):");
    let tags = multitasking.to_embedding_tags();
    println!("{:?}", tags);
    println!("Total unique tags: {}", tags.len());
    println!();
}

#[allow(dead_code)]
pub fn example_confidence_scoring() {
    // Example: Understanding confidence scores
    let contexts = vec![
        ("Development", ContextType::Development(DevelopmentType::Backend)),
        ("Communication", ContextType::Communication(CommunicationType::VideoMeeting)),
        ("Research", ContextType::Research(ResearchType::TechnicalResearch)),
        ("Creative", ContextType::Creative(CreativeType::UIDesign)),
        ("DataWork", ContextType::DataWork(DataWorkType::Spreadsheet)),
        ("Administration", ContextType::Administration(AdministrationType::Calendar)),
        ("Unknown", ContextType::Unknown),
    ];
    
    println!("Confidence Scores by Category:");
    for (name, context) in contexts {
        println!("  {}: {:.2}%", name, context.confidence_score() * 100.0);
    }
    println!();
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_bundle_id_detection() {
        let (context, confidence) = ContextType::from_app_bundle_id("com.microsoft.VSCode");
        assert!(matches!(context, ContextType::Development(_)));
        assert!(confidence > 0.5);
    }

    #[test]
    fn test_window_title_detection() {
        let (context, _) = ContextType::from_window_title("main.rs - my-project", None);
        assert!(matches!(context, ContextType::Development(DevelopmentType::Backend)));
    }

    #[test]
    fn test_embedding_tags() {
        let context = ContextType::Development(DevelopmentType::Frontend);
        let tags = context.to_embedding_tags();
        assert!(tags.contains(&"development".to_string()));
        assert!(tags.contains(&"frontend".to_string()));
    }

    #[test]
    fn test_context_hierarchy() {
        let context = ContextType::Development(DevelopmentType::Frontend);
        let hierarchy = ContextHierarchy::new(context);
        assert!(!hierarchy.children.is_empty());
        assert!(!hierarchy.related_contexts.is_empty());
    }

    #[test]
    fn test_confidence_scores() {
        let dev = ContextType::Development(DevelopmentType::Backend);
        let unknown = ContextType::Unknown;
        assert!(dev.confidence_score() > unknown.confidence_score());
    }

    #[test]
    fn test_display_trait() {
        let context = ContextType::Development(DevelopmentType::Frontend);
        let display = format!("{}", context);
        assert!(display.contains("Frontend Development"));
    }

    #[test]
    fn test_multitasking_context() {
        let contexts = vec![
            ContextType::Development(DevelopmentType::Frontend),
            ContextType::Research(ResearchType::APIDocumentation),
        ];
        let multi = ContextType::Multitasking(contexts);
        assert!(multi.confidence_score() > 0.0);
        assert!(multi.confidence_score() < 1.0);
    }
}

