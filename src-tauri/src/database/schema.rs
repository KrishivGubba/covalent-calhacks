//Database schema for NodeTable, DataTable, ActionTable
//DOCS: https://docs.google.com/document/d/1e8nFWbokazZwUgQcC4nOhiBGEElRfrEO1lkBVnMIC1k/edit?usp=sharing

use std::collections::HashMap;
use std::sync::Arc;
use tokio::sync::RwLock;
use serde::{Deserialize, Serialize};
use chrono::{DateTime, Utc, Duration};
use uuid::Uuid;

use super::connection::DatabaseManager;


pub enum DataType {
    Text,
    File,
    Image,
    Script,
    //add more data types when we support them
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct NodeTableEntry {
    pub node_uuid: Uuid,
    pub terminal: bool,
    pub metadata: String,
    pub tree_level: i32,
    pub confidence: f32,

    pub creation_timestamp: DateTime<Utc>,
    pub last_edit_timestamp: DateTime<Utc>,

    pub parent_uuid: Option<Uuid>, //keep it optional for root 
    pub children_uuids: Vec<Uuid>,
    
    // data in DataTableEntry
    // actions in ActionTableEntry
    pub data_uuid: Uuid,
    pub action_uuid: Option<Uuid>, //Only terminal nodes have actions
}

#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct DataTableEntry {
    pub node_uuid: Uuid,
    pub data_uuid: Uuid,
    
    pub data_type: DataType,
    pub data: serde_json::Value,

    pub creation_timestamp: DateTime<Utc>,
    pub last_edit_timestamp: DateTime<Utc>,
}

#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct ActionTableEntry {
    pub node_uuid: Uuid,
    pub action_uuid: Uuid,
    pub data_uuid: Uuid,
    //pub script_uuid: Option<Uuid>,

    pub action_type: String,
    pub action_data: serde_json::Value,

    pub creation_timestamp: DateTime<Utc>,
    pub last_edit_timestamp: DateTime<Utc>,
}

