// Demo file showing the enhanced ContextType system in action

use super::context_type::{ContextType, DevelopmentType, CommunicationType, ContextHierarchy};

#[allow(dead_code)]
pub fn run_demo() {
    println!("=== Enhanced ContextType System Demo ===\n");
    
    // Demo 1: Bundle ID Detection
    println!("📱 DEMO 1: Bundle ID Detection");
    println!("─────────────────────────────────");
    
    let apps = vec![
        "com.microsoft.VSCode",
        "us.zoom.xos",
        "com.figma.Desktop",
        "com.microsoft.Excel",
        "com.1password",
    ];
    
    for bundle_id in apps {
        let (context, confidence) = ContextType::from_app_bundle_id(bundle_id);
        println!("App: {}", bundle_id);
        println!("  Context: {}", context.category_name());
        println!("  Type: {}", context.subcategory_name());
        println!("  Confidence: {:.1}%", confidence * 100.0);
        println!();
    }
    
    // Demo 2: Window Title Detection
    println!("\n🪟 DEMO 2: Window Title Detection");
    println!("─────────────────────────────────");
    
    let windows = vec![
        "App.tsx - my-project - Visual Studio Code",
        "Pull Request #42: Add authentication - GitHub",
        "Sales Dashboard - Tableau",
        "Zoom Meeting - Project Standup",
    ];
    
    for title in windows {
        let (context, confidence) = ContextType::from_window_title(title, None);
        println!("Window: {}", title);
        println!("  Context: {}", context.category_name());
        println!("  Type: {}", context.subcategory_name());
        println!("  Confidence: {:.1}%", confidence * 100.0);
        println!();
    }
    
    // Demo 3: Embedding Tags
    println!("\n🏷️  DEMO 3: Embedding Tags");
    println!("─────────────────────────────────");
    
    let context = ContextType::Development(DevelopmentType::Frontend);
    let tags = context.to_embedding_tags();
    println!("Context: {}", context);
    println!("Tags: {}", tags.join(", "));
    println!("Total: {} tags", tags.len());
    println!();
    
    // Demo 4: Context Hierarchy
    println!("\n🌳 DEMO 4: Context Hierarchy");
    println!("─────────────────────────────────");
    
    let context = ContextType::Development(DevelopmentType::Backend);
    let hierarchy = ContextHierarchy::new(context.clone());
    
    println!("Current: {}", context.category_name());
    println!("Depth: {}", hierarchy.depth());
    println!("Children: {} options", hierarchy.children.len());
    println!("Related contexts:");
    for related in &hierarchy.related_contexts {
        println!("  • {}", related.category_name());
    }
    println!();
    
    // Demo 5: Display Trait
    println!("\n💬 DEMO 5: Human-Readable Descriptions");
    println!("─────────────────────────────────");
    
    let contexts = vec![
        ContextType::Development(DevelopmentType::Frontend),
        ContextType::Communication(CommunicationType::VideoMeeting),
    ];
    
    for ctx in contexts {
        println!("{}", ctx);
        println!();
    }
    
    // Demo 6: Confidence Scores
    println!("\n📊 DEMO 6: Confidence Scores by Category");
    println!("─────────────────────────────────");
    
    let test_contexts = vec![
        ("Development", ContextType::Development(DevelopmentType::Backend)),
        ("Communication", ContextType::Communication(CommunicationType::VideoMeeting)),
    ];
    
    for (name, ctx) in test_contexts {
        println!("{}: {:.1}%", name, ctx.confidence_score() * 100.0);
    }
    
    println!("\n=== Demo Complete ===\n");
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_demo_runs_without_panic() {
        // Just verify the demo can run without panicking
        run_demo();
    }
}

