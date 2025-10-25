use serde::{Deserialize, Serialize};
use std::fmt;

// Granular context type enum with nested categories
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq, Hash)]
pub enum ContextType {
    // Development contexts
    Development(DevelopmentType),
    
    // Communication contexts
    Communication(CommunicationType),
    
    // Research contexts
    Research(ResearchType),
    
    // Creative contexts
    Creative(CreativeType),
    
    // Data work contexts
    DataWork(DataWorkType),
    
    // Administration contexts
    Administration(AdministrationType),
    
    // Composite & fallback
    Multitasking(Vec<ContextType>),
    Unknown,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq, Hash)]
pub enum DevelopmentType {
    Frontend,
    Backend,
    Database,
    DevOps,
    Debugging,
    CodeReview,
    Documentation,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq, Hash)]
pub enum CommunicationType {
    VideoMeeting,
    AudioCall,
    InstantMessaging,
    EmailDrafting,
    SlackDiscussion,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq, Hash)]
pub enum ResearchType {
    TechnicalResearch,
    MarketResearch,
    AcademicReading,
    APIDocumentation,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq, Hash)]
pub enum CreativeType {
    UIDesign,
    GraphicDesign,
    VideoEditing,
    ContentWriting,
    Presentation,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq, Hash)]
pub enum DataWorkType {
    Spreadsheet,
    DataVisualization,
    SQLQuerying,
    DataCleaning,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq, Hash)]
pub enum AdministrationType {
    TaskManagement,
    Calendar,
    PasswordManager,
    SystemSettings,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct IntentAnalysis {
    pub app_name: String,
    pub action_description: String,  // 200-300 words for embedding
    pub context_type: ContextType,
    pub delta_analysis: DeltaAnalysis,
    pub confidence: f32,
    pub timestamp: i64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DeltaAnalysis {
    pub user_intent: String,         // High-level intent
    pub workflow_stage: String,      // Where in workflow
    pub key_changes: Vec<String>,    // Important changes detected
    pub automation_opportunities: Vec<String>,
    pub interaction_pattern: InteractionPattern,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum InteractionPattern {
    FormFilling { fields: Vec<String> },
    TextEditing { document_type: String },
    Navigation { between: Vec<String> },
    DataEntry { pattern: String },
    Reading { scroll_pattern: String },
    Clicking { frequency: String },
}

// Context hierarchy for parent-child relationships
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ContextHierarchy {
    pub current: ContextType,
    pub parent: Option<Box<ContextType>>,
    pub children: Vec<ContextType>,
    pub related_contexts: Vec<ContextType>,
}

impl ContextHierarchy {
    pub fn new(context: ContextType) -> Self {
        Self {
            current: context.clone(),
            parent: context.get_parent(),
            children: context.get_children(),
            related_contexts: context.get_related_contexts(),
        }
    }

    pub fn depth(&self) -> usize {
        // Count depth by traversing parent chain
        if self.parent.is_some() {
            1
        } else {
            0
        }
    }

    pub fn path(&self) -> Vec<String> {
        let mut path = Vec::new();
        
        // Add parent if exists
        if let Some(parent) = &self.parent {
            path.push(parent.to_string());
        }
        
        // Add current context
        path.push(self.current.to_string());
        
        path
    }
}

// Implementation of helper methods for ContextType
impl ContextType {
    /// Detect context from macOS bundle identifier
    pub fn from_app_bundle_id(bundle_id: &str) -> (Self, f32) {
        let bundle_id = bundle_id.to_lowercase();
        
        // Development tools
        if bundle_id.contains("vscode") || bundle_id.contains("com.microsoft.vscode") 
            || bundle_id == "com.exafunction.windsurf" {
            return (Self::Development(DevelopmentType::Frontend), 0.8);
        } else if bundle_id.contains("xcode") || bundle_id.contains("com.apple.dt.xcode") {
            return (Self::Development(DevelopmentType::Frontend), 0.75);
        } else if bundle_id.contains("intellij") || bundle_id.contains("pycharm") 
            || bundle_id.contains("webstorm") || bundle_id.contains("jetbrains") {
            return (Self::Development(DevelopmentType::Backend), 0.75);
        } else if bundle_id.contains("datagrip") || bundle_id.contains("sequel") 
            || bundle_id.contains("postico") || bundle_id.contains("tableplus") {
            return (Self::Development(DevelopmentType::Database), 0.85);
        } else if bundle_id.contains("docker") || bundle_id.contains("terminal") 
            || bundle_id == "com.apple.terminal" || bundle_id == "com.mitchellh.ghostty"
            || bundle_id.contains("sourcetree") || bundle_id.contains("com.torusknot.sourcetreenotmas") {
            return (Self::Development(DevelopmentType::DevOps), 0.7);
        }
        
        // Communication tools
        if bundle_id.contains("zoom") || bundle_id.contains("meet") 
            || bundle_id.contains("teams") || bundle_id.contains("us.zoom.xos") {
            return (Self::Communication(CommunicationType::VideoMeeting), 0.9);
        } else if bundle_id.contains("slack") || bundle_id == "com.tinyspeck.slackmacgap" {
            return (Self::Communication(CommunicationType::SlackDiscussion), 0.9);
        } else if bundle_id.contains("mail") || bundle_id.contains("outlook") 
            || bundle_id == "com.apple.mail" {
            return (Self::Communication(CommunicationType::EmailDrafting), 0.8);
        } else if bundle_id.contains("messages") || bundle_id.contains("telegram") 
            || bundle_id.contains("whatsapp") || bundle_id == "com.apple.mobilesms" {
            return (Self::Communication(CommunicationType::InstantMessaging), 0.85);
        }
        
        // Creative tools
        if bundle_id.contains("figma") || bundle_id.contains("sketch") {
            return (Self::Creative(CreativeType::UIDesign), 0.9);
        } else if bundle_id.contains("photoshop") || bundle_id.contains("illustrator") {
            return (Self::Creative(CreativeType::GraphicDesign), 0.9);
        } else if bundle_id.contains("premiere") || bundle_id.contains("finalcut") {
            return (Self::Creative(CreativeType::VideoEditing), 0.9);
        } else if bundle_id.contains("keynote") || bundle_id.contains("powerpoint") {
            return (Self::Creative(CreativeType::Presentation), 0.85);
        }
        
        // Data work tools
        if bundle_id.contains("excel") || bundle_id.contains("numbers") 
            || bundle_id.contains("sheets") {
            return (Self::DataWork(DataWorkType::Spreadsheet), 0.9);
        } else if bundle_id.contains("tableau") || bundle_id.contains("looker") {
            return (Self::DataWork(DataWorkType::DataVisualization), 0.9);
        }
        
        // Administration tools
        if bundle_id.contains("notion") || bundle_id.contains("trello") 
            || bundle_id.contains("asana") || bundle_id.contains("jira")
            || bundle_id == "notion.id" {
            return (Self::Administration(AdministrationType::TaskManagement), 0.85);
        } else if bundle_id.contains("calendar") || bundle_id.contains("fantastical")
            || bundle_id == "com.apple.ical" {
            return (Self::Administration(AdministrationType::Calendar), 0.9);
        } else if bundle_id.contains("1password") || bundle_id.contains("lastpass") 
            || bundle_id.contains("bitwarden") {
            return (Self::Administration(AdministrationType::PasswordManager), 0.95);
        } else if bundle_id.contains("settings") || bundle_id.contains("preferences")
            || bundle_id == "com.apple.systempreferences" {
            return (Self::Administration(AdministrationType::SystemSettings), 0.9);
        }
        
        // Research contexts (browsers need window title for better classification)
        if bundle_id.contains("safari") || bundle_id.contains("chrome") 
            || bundle_id.contains("firefox") || bundle_id == "com.brave.browser"
            || bundle_id == "com.google.chrome" || bundle_id == "com.apple.safari"
            || bundle_id == "org.mozilla.firefox" || bundle_id.contains("com.todesktop") {
            return (Self::Research(ResearchType::TechnicalResearch), 0.4);
        }
        
        // Media/Entertainment apps (classify as Unknown for now since no media category exists)
        if bundle_id.contains("spotify") || bundle_id == "com.spotify.client"
            || bundle_id.contains("music") || bundle_id.contains("netflix")
            || bundle_id.contains("youtube") {
            return (Self::Unknown, 0.2); // Low confidence since no proper category
        }
        
        (Self::Unknown, 0.0)
    }
    
    /// Infer context from window title
    pub fn from_window_title(title: &str, bundle_id: Option<&str>) -> (Self, f32) {
        let title_lower = title.to_lowercase();
        
        // Development indicators
        if title_lower.contains(".js") || title_lower.contains(".jsx") 
            || title_lower.contains(".ts") || title_lower.contains(".tsx")
            || title_lower.contains(".vue") || title_lower.contains(".svelte") {
            return (Self::Development(DevelopmentType::Frontend), 0.8);
        } else if title_lower.contains(".py") || title_lower.contains(".go") 
            || title_lower.contains(".rs") || title_lower.contains(".java") {
            return (Self::Development(DevelopmentType::Backend), 0.8);
        } else if title_lower.contains(".sql") || title_lower.contains("query") 
            || title_lower.contains("database") {
            return (Self::Development(DevelopmentType::Database), 0.75);
        } else if title_lower.contains("debug") || title_lower.contains("breakpoint") {
            return (Self::Development(DevelopmentType::Debugging), 0.85);
        } else if title_lower.contains("pull request") || title_lower.contains("pr #") 
            || title_lower.contains("code review") {
            return (Self::Development(DevelopmentType::CodeReview), 0.9);
        } else if title_lower.contains("readme") || title_lower.contains(".md") 
            || title_lower.contains("documentation") {
            return (Self::Development(DevelopmentType::Documentation), 0.75);
        }
        
        // Research indicators
        if title_lower.contains("documentation") || title_lower.contains("api reference") 
            || title_lower.contains("docs") {
            return (Self::Research(ResearchType::APIDocumentation), 0.8);
        } else if title_lower.contains("arxiv") || title_lower.contains("paper") 
            || title_lower.contains("research") || title_lower.contains("journal") {
            return (Self::Research(ResearchType::AcademicReading), 0.8);
        } else if title_lower.contains("market") || title_lower.contains("competitor") 
            || title_lower.contains("analysis") {
            return (Self::Research(ResearchType::MarketResearch), 0.7);
        } else if title_lower.contains("stack overflow") || title_lower.contains("github") 
            || title_lower.contains("tutorial") {
            return (Self::Research(ResearchType::TechnicalResearch), 0.75);
        }
        
        // Communication indicators
        if title_lower.contains("zoom meeting") || title_lower.contains("google meet") {
            return (Self::Communication(CommunicationType::VideoMeeting), 0.95);
        } else if title_lower.contains("compose") || title_lower.contains("new message") 
            || title_lower.contains("draft") {
            return (Self::Communication(CommunicationType::EmailDrafting), 0.8);
        }
        
        // Creative indicators
        if title_lower.contains("design") || title_lower.contains("mockup") {
            return (Self::Creative(CreativeType::UIDesign), 0.7);
        } else if title_lower.contains("presentation") || title_lower.contains("slide") {
            return (Self::Creative(CreativeType::Presentation), 0.8);
        } else if title_lower.contains("article") || title_lower.contains("blog") 
            || title_lower.contains("post") {
            return (Self::Creative(CreativeType::ContentWriting), 0.7);
        }
        
        // Data work indicators
        if title_lower.contains("spreadsheet") || title_lower.contains(".xlsx") 
            || title_lower.contains(".csv") {
            return (Self::DataWork(DataWorkType::Spreadsheet), 0.8);
        } else if title_lower.contains("dashboard") || title_lower.contains("chart") 
            || title_lower.contains("visualization") {
            return (Self::DataWork(DataWorkType::DataVisualization), 0.8);
        }
        
        // Fall back to bundle ID if available
        if let Some(bid) = bundle_id {
            return Self::from_app_bundle_id(bid);
        }
        
        (Self::Unknown, 0.0)
    }
    
    /// Get confidence score for the classification
    pub fn confidence_score(&self) -> f32 {
        match self {
            Self::Development(_) => 0.75,
            Self::Communication(_) => 0.85,
            Self::Research(_) => 0.65,
            Self::Creative(_) => 0.80,
            Self::DataWork(_) => 0.85,
            Self::Administration(_) => 0.90,
            Self::Multitasking(contexts) => {
                if contexts.is_empty() {
                    0.3
                } else {
                    contexts.iter()
                        .map(|c| c.confidence_score())
                        .sum::<f32>() / contexts.len() as f32 * 0.8
                }
            },
            Self::Unknown => 0.0,
        }
    }
    
    /// Return relevant tags for vector search and embeddings
    pub fn to_embedding_tags(&self) -> Vec<String> {
        let mut tags = Vec::new();
        
        match self {
            Self::Development(dev_type) => {
                tags.push("development".to_string());
                tags.push("coding".to_string());
                tags.push("programming".to_string());
                
                match dev_type {
                    DevelopmentType::Frontend => {
                        tags.extend(vec![
                            "frontend".to_string(),
                            "ui".to_string(),
                            "javascript".to_string(),
                            "react".to_string(),
                            "web".to_string(),
                        ]);
                    },
                    DevelopmentType::Backend => {
                        tags.extend(vec![
                            "backend".to_string(),
                            "server".to_string(),
                            "api".to_string(),
                            "database".to_string(),
                        ]);
                    },
                    DevelopmentType::Database => {
                        tags.extend(vec![
                            "database".to_string(),
                            "sql".to_string(),
                            "query".to_string(),
                            "data".to_string(),
                        ]);
                    },
                    DevelopmentType::DevOps => {
                        tags.extend(vec![
                            "devops".to_string(),
                            "deployment".to_string(),
                            "infrastructure".to_string(),
                            "docker".to_string(),
                            "kubernetes".to_string(),
                        ]);
                    },
                    DevelopmentType::Debugging => {
                        tags.extend(vec![
                            "debugging".to_string(),
                            "troubleshooting".to_string(),
                            "error".to_string(),
                            "fix".to_string(),
                        ]);
                    },
                    DevelopmentType::CodeReview => {
                        tags.extend(vec![
                            "code-review".to_string(),
                            "pull-request".to_string(),
                            "collaboration".to_string(),
                        ]);
                    },
                    DevelopmentType::Documentation => {
                        tags.extend(vec![
                            "documentation".to_string(),
                            "readme".to_string(),
                            "writing".to_string(),
                        ]);
                    },
                }
            },
            Self::Communication(comm_type) => {
                tags.push("communication".to_string());
                tags.push("collaboration".to_string());
                
                match comm_type {
                    CommunicationType::VideoMeeting => {
                        tags.extend(vec![
                            "meeting".to_string(),
                            "video-call".to_string(),
                            "zoom".to_string(),
                            "discussion".to_string(),
                        ]);
                    },
                    CommunicationType::AudioCall => {
                        tags.extend(vec![
                            "call".to_string(),
                            "audio".to_string(),
                            "phone".to_string(),
                        ]);
                    },
                    CommunicationType::InstantMessaging => {
                        tags.extend(vec![
                            "messaging".to_string(),
                            "chat".to_string(),
                            "instant-message".to_string(),
                        ]);
                    },
                    CommunicationType::EmailDrafting => {
                        tags.extend(vec![
                            "email".to_string(),
                            "writing".to_string(),
                            "correspondence".to_string(),
                        ]);
                    },
                    CommunicationType::SlackDiscussion => {
                        tags.extend(vec![
                            "slack".to_string(),
                            "team-chat".to_string(),
                            "discussion".to_string(),
                        ]);
                    },
                }
            },
            Self::Research(research_type) => {
                tags.push("research".to_string());
                tags.push("learning".to_string());
                tags.push("reading".to_string());
                
                match research_type {
                    ResearchType::TechnicalResearch => {
                        tags.extend(vec![
                            "technical".to_string(),
                            "documentation".to_string(),
                            "tutorial".to_string(),
                            "stack-overflow".to_string(),
                        ]);
                    },
                    ResearchType::MarketResearch => {
                        tags.extend(vec![
                            "market".to_string(),
                            "competitor".to_string(),
                            "analysis".to_string(),
                            "business".to_string(),
                        ]);
                    },
                    ResearchType::AcademicReading => {
                        tags.extend(vec![
                            "academic".to_string(),
                            "paper".to_string(),
                            "journal".to_string(),
                            "study".to_string(),
                        ]);
                    },
                    ResearchType::APIDocumentation => {
                        tags.extend(vec![
                            "api".to_string(),
                            "documentation".to_string(),
                            "reference".to_string(),
                            "integration".to_string(),
                        ]);
                    },
                }
            },
            Self::Creative(creative_type) => {
                tags.push("creative".to_string());
                tags.push("design".to_string());
                
                match creative_type {
                    CreativeType::UIDesign => {
                        tags.extend(vec![
                            "ui-design".to_string(),
                            "interface".to_string(),
                            "mockup".to_string(),
                            "figma".to_string(),
                        ]);
                    },
                    CreativeType::GraphicDesign => {
                        tags.extend(vec![
                            "graphic-design".to_string(),
                            "illustration".to_string(),
                            "visual".to_string(),
                        ]);
                    },
                    CreativeType::VideoEditing => {
                        tags.extend(vec![
                            "video".to_string(),
                            "editing".to_string(),
                            "multimedia".to_string(),
                        ]);
                    },
                    CreativeType::ContentWriting => {
                        tags.extend(vec![
                            "writing".to_string(),
                            "content".to_string(),
                            "article".to_string(),
                            "blog".to_string(),
                        ]);
                    },
                    CreativeType::Presentation => {
                        tags.extend(vec![
                            "presentation".to_string(),
                            "slides".to_string(),
                            "keynote".to_string(),
                        ]);
                    },
                }
            },
            Self::DataWork(data_type) => {
                tags.push("data".to_string());
                tags.push("analysis".to_string());
                
                match data_type {
                    DataWorkType::Spreadsheet => {
                        tags.extend(vec![
                            "spreadsheet".to_string(),
                            "excel".to_string(),
                            "numbers".to_string(),
                        ]);
                    },
                    DataWorkType::DataVisualization => {
                        tags.extend(vec![
                            "visualization".to_string(),
                            "chart".to_string(),
                            "dashboard".to_string(),
                        ]);
                    },
                    DataWorkType::SQLQuerying => {
                        tags.extend(vec![
                            "sql".to_string(),
                            "query".to_string(),
                            "database".to_string(),
                        ]);
                    },
                    DataWorkType::DataCleaning => {
                        tags.extend(vec![
                            "data-cleaning".to_string(),
                            "preprocessing".to_string(),
                            "etl".to_string(),
                        ]);
                    },
                }
            },
            Self::Administration(admin_type) => {
                tags.push("administration".to_string());
                tags.push("productivity".to_string());
                
                match admin_type {
                    AdministrationType::TaskManagement => {
                        tags.extend(vec![
                            "tasks".to_string(),
                            "todo".to_string(),
                            "project-management".to_string(),
                        ]);
                    },
                    AdministrationType::Calendar => {
                        tags.extend(vec![
                            "calendar".to_string(),
                            "scheduling".to_string(),
                            "events".to_string(),
                        ]);
                    },
                    AdministrationType::PasswordManager => {
                        tags.extend(vec![
                            "password".to_string(),
                            "security".to_string(),
                            "credentials".to_string(),
                        ]);
                    },
                    AdministrationType::SystemSettings => {
                        tags.extend(vec![
                            "settings".to_string(),
                            "configuration".to_string(),
                            "system".to_string(),
                        ]);
                    },
                }
            },
            Self::Multitasking(contexts) => {
                tags.push("multitasking".to_string());
                tags.push("multiple-contexts".to_string());
                
                for context in contexts {
                    tags.extend(context.to_embedding_tags());
                }
            },
            Self::Unknown => {
                tags.push("unknown".to_string());
                tags.push("unclassified".to_string());
            },
        }
        
        // Remove duplicates
        tags.sort();
        tags.dedup();
        tags
    }
    
    /// Get parent context type (for hierarchy)
    pub fn get_parent(&self) -> Option<Box<ContextType>> {
        match self {
            Self::Development(_) |
            Self::Communication(_) |
            Self::Research(_) |
            Self::Creative(_) |
            Self::DataWork(_) |
            Self::Administration(_) => None,
            Self::Multitasking(_) | Self::Unknown => None,
        }
    }
    
    /// Get possible child context types
    pub fn get_children(&self) -> Vec<ContextType> {
        match self {
            Self::Development(_) => vec![
                Self::Development(DevelopmentType::Frontend),
                Self::Development(DevelopmentType::Backend),
                Self::Development(DevelopmentType::Database),
                Self::Development(DevelopmentType::DevOps),
                Self::Development(DevelopmentType::Debugging),
                Self::Development(DevelopmentType::CodeReview),
                Self::Development(DevelopmentType::Documentation),
            ],
            Self::Communication(_) => vec![
                Self::Communication(CommunicationType::VideoMeeting),
                Self::Communication(CommunicationType::AudioCall),
                Self::Communication(CommunicationType::InstantMessaging),
                Self::Communication(CommunicationType::EmailDrafting),
                Self::Communication(CommunicationType::SlackDiscussion),
            ],
            Self::Research(_) => vec![
                Self::Research(ResearchType::TechnicalResearch),
                Self::Research(ResearchType::MarketResearch),
                Self::Research(ResearchType::AcademicReading),
                Self::Research(ResearchType::APIDocumentation),
            ],
            Self::Creative(_) => vec![
                Self::Creative(CreativeType::UIDesign),
                Self::Creative(CreativeType::GraphicDesign),
                Self::Creative(CreativeType::VideoEditing),
                Self::Creative(CreativeType::ContentWriting),
                Self::Creative(CreativeType::Presentation),
            ],
            Self::DataWork(_) => vec![
                Self::DataWork(DataWorkType::Spreadsheet),
                Self::DataWork(DataWorkType::DataVisualization),
                Self::DataWork(DataWorkType::SQLQuerying),
                Self::DataWork(DataWorkType::DataCleaning),
            ],
            Self::Administration(_) => vec![
                Self::Administration(AdministrationType::TaskManagement),
                Self::Administration(AdministrationType::Calendar),
                Self::Administration(AdministrationType::PasswordManager),
                Self::Administration(AdministrationType::SystemSettings),
            ],
            _ => vec![],
        }
    }
    
    /// Get related context types that often occur together
    pub fn get_related_contexts(&self) -> Vec<ContextType> {
        match self {
            Self::Development(dev_type) => match dev_type {
                DevelopmentType::Frontend => vec![
                    Self::Development(DevelopmentType::Backend),
                    Self::Research(ResearchType::APIDocumentation),
                    Self::Creative(CreativeType::UIDesign),
                ],
                DevelopmentType::Backend => vec![
                    Self::Development(DevelopmentType::Database),
                    Self::Development(DevelopmentType::Frontend),
                    Self::Research(ResearchType::APIDocumentation),
                ],
                DevelopmentType::Database => vec![
                    Self::Development(DevelopmentType::Backend),
                    Self::DataWork(DataWorkType::SQLQuerying),
                ],
                DevelopmentType::DevOps => vec![
                    Self::Development(DevelopmentType::Backend),
                    Self::Administration(AdministrationType::SystemSettings),
                ],
                DevelopmentType::Debugging => vec![
                    Self::Development(DevelopmentType::Frontend),
                    Self::Development(DevelopmentType::Backend),
                    Self::Research(ResearchType::TechnicalResearch),
                ],
                DevelopmentType::CodeReview => vec![
                    Self::Development(DevelopmentType::Frontend),
                    Self::Development(DevelopmentType::Backend),
                    Self::Communication(CommunicationType::SlackDiscussion),
                ],
                DevelopmentType::Documentation => vec![
                    Self::Development(DevelopmentType::Frontend),
                    Self::Development(DevelopmentType::Backend),
                    Self::Creative(CreativeType::ContentWriting),
                ],
            },
            Self::Communication(_) => vec![
                Self::Administration(AdministrationType::Calendar),
                Self::Administration(AdministrationType::TaskManagement),
            ],
            Self::Research(_) => vec![
                Self::Development(DevelopmentType::Frontend),
                Self::Development(DevelopmentType::Backend),
                Self::Creative(CreativeType::ContentWriting),
            ],
            Self::Creative(creative_type) => match creative_type {
                CreativeType::UIDesign => vec![
                    Self::Development(DevelopmentType::Frontend),
                    Self::Creative(CreativeType::GraphicDesign),
                ],
                CreativeType::Presentation => vec![
                    Self::Creative(CreativeType::ContentWriting),
                    Self::DataWork(DataWorkType::DataVisualization),
                ],
                _ => vec![],
            },
            Self::DataWork(_) => vec![
                Self::Development(DevelopmentType::Database),
                Self::Research(ResearchType::TechnicalResearch),
            ],
            Self::Administration(_) => vec![],
            Self::Multitasking(_) | Self::Unknown => vec![],
        }
    }
    
    /// Get human-readable category name
    pub fn category_name(&self) -> &str {
        match self {
            Self::Development(_) => "Development",
            Self::Communication(_) => "Communication",
            Self::Research(_) => "Research",
            Self::Creative(_) => "Creative",
            Self::DataWork(_) => "Data Work",
            Self::Administration(_) => "Administration",
            Self::Multitasking(_) => "Multitasking",
            Self::Unknown => "Unknown",
        }
    }
    
    /// Get human-readable subcategory name
    pub fn subcategory_name(&self) -> String {
        match self {
            Self::Development(dev_type) => format!("{:?}", dev_type),
            Self::Communication(comm_type) => format!("{:?}", comm_type),
            Self::Research(research_type) => format!("{:?}", research_type),
            Self::Creative(creative_type) => format!("{:?}", creative_type),
            Self::DataWork(data_type) => format!("{:?}", data_type),
            Self::Administration(admin_type) => format!("{:?}", admin_type),
            Self::Multitasking(_) => "Multiple Contexts".to_string(),
            Self::Unknown => "Unknown".to_string(),
        }
    }
}

// Implement Display trait for human-readable output
impl fmt::Display for ContextType {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Development(dev_type) => {
                let description = match dev_type {
                    DevelopmentType::Frontend => "Frontend Development - Working with user interfaces, HTML, CSS, JavaScript frameworks",
                    DevelopmentType::Backend => "Backend Development - Server-side logic, APIs, business logic implementation",
                    DevelopmentType::Database => "Database Work - Schema design, queries, data modeling",
                    DevelopmentType::DevOps => "DevOps - Infrastructure, deployment, CI/CD, containerization",
                    DevelopmentType::Debugging => "Debugging - Troubleshooting issues, analyzing logs, fixing bugs",
                    DevelopmentType::CodeReview => "Code Review - Reviewing pull requests, providing feedback on code",
                    DevelopmentType::Documentation => "Documentation - Writing technical documentation, README files, guides",
                };
                write!(f, "{}", description)
            },
            Self::Communication(comm_type) => {
                let description = match comm_type {
                    CommunicationType::VideoMeeting => "Video Meeting - Participating in video conference calls",
                    CommunicationType::AudioCall => "Audio Call - Voice-only communication",
                    CommunicationType::InstantMessaging => "Instant Messaging - Real-time text communication",
                    CommunicationType::EmailDrafting => "Email Drafting - Composing and sending emails",
                    CommunicationType::SlackDiscussion => "Slack Discussion - Team chat and collaboration",
                };
                write!(f, "{}", description)
            },
            Self::Research(research_type) => {
                let description = match research_type {
                    ResearchType::TechnicalResearch => "Technical Research - Learning about technologies, reading documentation",
                    ResearchType::MarketResearch => "Market Research - Analyzing competitors, market trends, business intelligence",
                    ResearchType::AcademicReading => "Academic Reading - Reading papers, journals, academic content",
                    ResearchType::APIDocumentation => "API Documentation - Reading and understanding API references",
                };
                write!(f, "{}", description)
            },
            Self::Creative(creative_type) => {
                let description = match creative_type {
                    CreativeType::UIDesign => "UI Design - Designing user interfaces, creating mockups",
                    CreativeType::GraphicDesign => "Graphic Design - Creating visual content, illustrations",
                    CreativeType::VideoEditing => "Video Editing - Editing and producing video content",
                    CreativeType::ContentWriting => "Content Writing - Writing articles, blog posts, marketing content",
                    CreativeType::Presentation => "Presentation - Creating and editing presentation slides",
                };
                write!(f, "{}", description)
            },
            Self::DataWork(data_type) => {
                let description = match data_type {
                    DataWorkType::Spreadsheet => "Spreadsheet Work - Working with Excel, Google Sheets, data in tabular format",
                    DataWorkType::DataVisualization => "Data Visualization - Creating charts, dashboards, visual data representations",
                    DataWorkType::SQLQuerying => "SQL Querying - Writing and executing database queries",
                    DataWorkType::DataCleaning => "Data Cleaning - Preprocessing, transforming, and cleaning datasets",
                };
                write!(f, "{}", description)
            },
            Self::Administration(admin_type) => {
                let description = match admin_type {
                    AdministrationType::TaskManagement => "Task Management - Managing todos, projects, tracking work",
                    AdministrationType::Calendar => "Calendar - Scheduling events, managing appointments",
                    AdministrationType::PasswordManager => "Password Manager - Managing credentials and secrets",
                    AdministrationType::SystemSettings => "System Settings - Configuring system preferences and settings",
                };
                write!(f, "{}", description)
            },
            Self::Multitasking(contexts) => {
                write!(f, "Multitasking across {} contexts", contexts.len())
            },
            Self::Unknown => write!(f, "Unknown context - Unable to classify current activity"),
        }
    }
}

impl fmt::Display for DevelopmentType {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{:?}", self)
    }
}

impl fmt::Display for CommunicationType {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{:?}", self)
    }
}

impl fmt::Display for ResearchType {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{:?}", self)
    }
}

impl fmt::Display for CreativeType {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{:?}", self)
    }
}

impl fmt::Display for DataWorkType {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{:?}", self)
    }
}

impl fmt::Display for AdministrationType {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{:?}", self)
    }
}