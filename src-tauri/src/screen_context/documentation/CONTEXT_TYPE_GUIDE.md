# Enhanced ContextType System Guide

## Overview

The enhanced ContextType system provides a comprehensive, granular way to classify and understand user activity contexts on macOS. It uses a hierarchical categorization system with intelligent detection methods and rich metadata generation for vector search and embeddings.

## Architecture

### Core Components

1. **ContextType Enum** - Main categorization system with nested subtypes
2. **Helper Methods** - Detection and classification utilities
3. **ContextHierarchy** - Parent-child relationship management
4. **Display Traits** - Human-readable descriptions

## Categories and Subcategories

### 1. Development
Sub-types for software development activities:
- **Frontend** - UI work with JavaScript, React, Vue, Svelte, etc.
- **Backend** - Server-side logic, APIs, business logic
- **Database** - Schema design, queries, data modeling
- **DevOps** - Infrastructure, deployment, CI/CD, containers
- **Debugging** - Troubleshooting, log analysis, bug fixing
- **CodeReview** - Pull request reviews, code feedback
- **Documentation** - Technical docs, README files, guides

### 2. Communication
Sub-types for collaborative activities:
- **VideoMeeting** - Zoom, Google Meet, Teams calls
- **AudioCall** - Voice-only communication
- **InstantMessaging** - Text chat, WhatsApp, Telegram
- **EmailDrafting** - Composing and sending emails
- **SlackDiscussion** - Team chat and collaboration

### 3. Research
Sub-types for learning and investigation:
- **TechnicalResearch** - Stack Overflow, tutorials, tech blogs
- **MarketResearch** - Competitor analysis, business intelligence
- **AcademicReading** - Papers, journals, academic content
- **APIDocumentation** - Reading API references and integration guides

### 4. Creative
Sub-types for creative work:
- **UIDesign** - Interface design, mockups (Figma, Sketch)
- **GraphicDesign** - Visual content, illustrations
- **VideoEditing** - Video production and editing
- **ContentWriting** - Articles, blogs, marketing content
- **Presentation** - Slides creation and editing

### 5. DataWork
Sub-types for data-related tasks:
- **Spreadsheet** - Excel, Google Sheets work
- **DataVisualization** - Charts, dashboards, visual analytics
- **SQLQuerying** - Database queries and analysis
- **DataCleaning** - Preprocessing, transforming datasets

### 6. Administration
Sub-types for productivity tasks:
- **TaskManagement** - Todos, project tracking (Notion, Trello, Jira)
- **Calendar** - Scheduling, event management
- **PasswordManager** - Credential management (1Password, LastPass)
- **SystemSettings** - Configuration and preferences

### 7. Special Types
- **Multitasking** - Multiple contexts active simultaneously
- **Unknown** - Unable to classify activity

## Key Methods

### Detection Methods

#### `from_app_bundle_id(bundle_id: &str) -> (ContextType, f32)`
Detects context from macOS application bundle identifiers.

```rust
let (context, confidence) = ContextType::from_app_bundle_id("com.microsoft.VSCode");
// Returns: (Development(Frontend), 0.7)
```

**Supported Bundle IDs:**
- Development: vscode, xcode, intellij, pycharm, webstorm, datagrip, etc.
- Communication: zoom, slack, mail, outlook, messages, telegram, etc.
- Creative: figma, sketch, photoshop, illustrator, premiere, etc.
- Data: excel, numbers, tableau, looker, etc.
- Admin: notion, trello, asana, jira, calendar, 1password, etc.

#### `from_window_title(title: &str, bundle_id: Option<&str>) -> (ContextType, f32)`
Infers context from window titles with optional bundle ID fallback.

```rust
let (context, confidence) = ContextType::from_window_title(
    "App.tsx - my-project - Visual Studio Code",
    Some("com.microsoft.VSCode")
);
// Returns: (Development(Frontend), 0.8)
```

**Detection Patterns:**
- File extensions: `.js`, `.tsx`, `.py`, `.rs`, `.sql`, etc.
- Keywords: "debug", "pull request", "query", "dashboard", etc.
- Domain-specific terms: "zoom meeting", "design", "spreadsheet", etc.

### Metadata Methods

#### `confidence_score() -> f32`
Returns base confidence score for the context type (0.0 - 1.0).

```rust
let context = ContextType::Development(DevelopmentType::Backend);
let score = context.confidence_score(); // 0.75
```

**Score Ranges:**
- Administration: 0.90 (highest)
- Communication: 0.85
- DataWork: 0.85
- Creative: 0.80
- Development: 0.75
- Research: 0.65 (more ambiguous)
- Unknown: 0.0

#### `to_embedding_tags() -> Vec<String>`
Generates relevant tags for vector search and semantic embeddings.

```rust
let context = ContextType::Development(DevelopmentType::Frontend);
let tags = context.to_embedding_tags();
// Returns: ["coding", "development", "frontend", "javascript", 
//           "programming", "react", "ui", "web"]
```

**Features:**
- Hierarchical tags (both category and subcategory)
- Domain-specific keywords
- Common tools and technologies
- Automatically deduplicated and sorted

### Hierarchy Methods

#### `get_parent() -> Option<Box<ContextType>>`
Returns parent context (currently returns None as categories are top-level).

#### `get_children() -> Vec<ContextType>`
Returns all possible subcategories for a context type.

```rust
let context = ContextType::Development(DevelopmentType::Frontend);
let children = context.get_children();
// Returns all 7 DevelopmentType variants
```

#### `get_related_contexts() -> Vec<ContextType>`
Returns contexts that often occur together or are related.

```rust
let context = ContextType::Development(DevelopmentType::Frontend);
let related = context.get_related_contexts();
// Returns: [Development(Backend), Research(APIDocumentation), Creative(UIDesign)]
```

**Relationships:**
- Frontend ↔ Backend, UIDesign, API Documentation
- Backend ↔ Database, Frontend, API Documentation
- Debugging ↔ Frontend/Backend, Technical Research
- CodeReview ↔ Frontend/Backend, Slack Discussion
- UIDesign ↔ Frontend, Graphic Design
- And more...

### Display Methods

#### `category_name() -> &str`
Returns the top-level category name.

```rust
let context = ContextType::Development(DevelopmentType::Backend);
println!("{}", context.category_name()); // "Development"
```

#### `subcategory_name() -> String`
Returns the subcategory name.

```rust
let context = ContextType::Development(DevelopmentType::Backend);
println!("{}", context.subcategory_name()); // "Backend"
```

#### Display Trait Implementation
Full human-readable descriptions with context.

```rust
let context = ContextType::Development(DevelopmentType::Frontend);
println!("{}", context);
// Prints: "Frontend Development - Working with user interfaces, HTML, CSS, JavaScript frameworks"
```

## ContextHierarchy Struct

Represents parent-child relationships and related contexts.

### Creating a Hierarchy

```rust
let context = ContextType::Development(DevelopmentType::Frontend);
let hierarchy = ContextHierarchy::new(context);
```

### Methods

#### `depth() -> usize`
Returns hierarchy depth (currently 0 for all as categories are top-level).

#### `path() -> Vec<String>`
Returns full hierarchical path as strings.

```rust
let path = hierarchy.path();
// Returns: ["Frontend Development - Working with..."]
```

### Fields

```rust
pub struct ContextHierarchy {
    pub current: ContextType,           // Current context
    pub parent: Option<Box<ContextType>>, // Parent (if any)
    pub children: Vec<ContextType>,      // All possible children
    pub related_contexts: Vec<ContextType>, // Related contexts
}
```

## Usage Examples

### Example 1: Application Monitoring

```rust
use crate::screen_context::contextType::ContextType;

fn analyze_active_app(bundle_id: &str, window_title: &str) {
    // Try bundle ID first
    let (context_from_bundle, conf1) = ContextType::from_app_bundle_id(bundle_id);
    
    // Try window title for more specificity
    let (context_from_title, conf2) = ContextType::from_window_title(
        window_title, 
        Some(bundle_id)
    );
    
    // Use the one with higher confidence
    let (context, confidence) = if conf2 > conf1 {
        (context_from_title, conf2)
    } else {
        (context_from_bundle, conf1)
    };
    
    println!("Detected: {} ({}% confident)", 
        context.category_name(), 
        (confidence * 100.0) as u32
    );
    
    // Generate tags for embedding
    let tags = context.to_embedding_tags();
    // Store tags for vector search...
}
```

### Example 2: Context-Aware Suggestions

```rust
use crate::screen_context::contextType::{ContextType, ContextHierarchy};

fn suggest_next_actions(current: ContextType) {
    let hierarchy = ContextHierarchy::new(current.clone());
    
    println!("Current Activity: {}", current);
    println!("\nYou might also need:");
    
    for related in hierarchy.related_contexts {
        println!("  • {}", related.category_name());
    }
}
```

### Example 3: Multitasking Detection

```rust
use crate::screen_context::contextType::ContextType;

fn detect_multitasking(recent_contexts: Vec<ContextType>) -> ContextType {
    if recent_contexts.len() > 2 {
        // Check if contexts are different categories
        let unique_categories: std::collections::HashSet<_> = 
            recent_contexts.iter()
                .map(|c| c.category_name())
                .collect();
        
        if unique_categories.len() > 1 {
            return ContextType::Multitasking(recent_contexts);
        }
    }
    
    // Return most recent single context
    recent_contexts.last().cloned()
        .unwrap_or(ContextType::Unknown)
}
```

### Example 4: Activity Logging

```rust
use crate::screen_context::contextType::ContextType;

fn log_activity(context: &ContextType, duration: u64) {
    let tags = context.to_embedding_tags();
    
    println!("Activity Log:");
    println!("  Category: {}", context.category_name());
    println!("  Type: {}", context.subcategory_name());
    println!("  Duration: {} seconds", duration);
    println!("  Confidence: {:.1}%", context.confidence_score() * 100.0);
    println!("  Tags: {}", tags.join(", "));
    println!("  Description: {}", context);
}
```

## Best Practices

### 1. Confidence Thresholds
```rust
const MIN_CONFIDENCE: f32 = 0.5;

let (context, confidence) = ContextType::from_window_title(title, bundle_id);
if confidence < MIN_CONFIDENCE {
    // Fall back to manual classification or Unknown
    context = ContextType::Unknown;
}
```

### 2. Combining Detection Methods
Always try multiple detection methods and use the most confident result:

```rust
let detections = vec![
    ContextType::from_app_bundle_id(bundle_id),
    ContextType::from_window_title(window_title, Some(bundle_id)),
];

let best = detections.into_iter()
    .max_by(|a, b| a.1.partial_cmp(&b.1).unwrap())
    .unwrap();
```

### 3. Tag Generation for Search
Use embedding tags to improve semantic search:

```rust
let tags = context.to_embedding_tags();
let search_query = format!("{} {}", 
    context.category_name(), 
    tags.join(" ")
);
// Use search_query for vector similarity search
```

### 4. Related Context Suggestions
Proactively suggest related tools or contexts:

```rust
let related = context.get_related_contexts();
if !related.is_empty() {
    println!("Related activities you might switch to:");
    for ctx in related {
        println!("  - {}", ctx.category_name());
    }
}
```

## Testing

The module includes comprehensive tests in `context_examples.rs`:

```bash
cargo test --lib screen_context::context_examples::tests
```

### Test Coverage
- Bundle ID detection accuracy
- Window title pattern matching
- Embedding tag generation
- Context hierarchy relationships
- Confidence score calculations
- Display trait formatting
- Multitasking context handling

## Future Enhancements

1. **Machine Learning Integration**
   - Train model on user-specific patterns
   - Adaptive confidence scoring
   - Custom context type creation

2. **Temporal Context Analysis**
   - Time-of-day patterns
   - Context switching frequency
   - Activity duration modeling

3. **Multi-Application Contexts**
   - Cross-application workflows
   - Application switching patterns
   - Composite activity detection

4. **User Preferences**
   - Custom category mappings
   - Confidence threshold tuning
   - Tag customization

## API Stability

The core API is stable, but the following may change:
- Confidence score calculations (as we gather more data)
- Bundle ID mappings (new applications)
- Tag generation logic (improved relevance)
- Related context relationships (refined understanding)

## Contributing

When adding new applications or patterns:

1. Add bundle ID mapping in `from_app_bundle_id()`
2. Add window title pattern in `from_window_title()`
3. Update embedding tags in `to_embedding_tags()`
4. Add related contexts in `get_related_contexts()`
5. Update tests in `context_examples.rs`

## Performance Notes

- Bundle ID detection: O(1) - Fast string matching
- Window title detection: O(1) - Fast pattern matching
- Tag generation: O(n) where n = number of tags
- Hierarchy creation: O(m) where m = number of related contexts

All operations are lightweight and suitable for real-time monitoring.

