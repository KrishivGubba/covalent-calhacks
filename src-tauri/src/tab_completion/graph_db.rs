use anyhow::{Result, Context as AnyhowContext};
use rusqlite::{Connection, params};
use std::sync::{Arc, Mutex};

/// Direct SQLite access to graph.db for fast context retrieval
/// Bypasses Flask API for prediction queries
pub struct GraphDatabase {
    conn: Arc<Mutex<Connection>>,
}

#[derive(Debug, Clone)]
pub struct NodeData {
    pub node_uuid: String,
    pub metadata: String,
    pub parent_uuid: Option<String>,
    pub data_entries: Vec<DataEntry>,
}

#[derive(Debug, Clone)]
pub struct DataEntry {
    pub key: Option<String>,
    pub data_type: String,
    pub info: String,
}

impl GraphDatabase {
    /// Create a new GraphDatabase connection
    pub fn new(db_path: String) -> Result<Self> {
        let conn = Connection::open(&db_path)
            .with_context(|| format!("Failed to open graph.db at: {}", db_path))?;

        Ok(Self {
            conn: Arc::new(Mutex::new(conn)),
        })
    }

    /// Query nodes by metadata substring (simple but effective)
    /// Returns nodes whose metadata contains the query string
    pub fn search_nodes(&self, query: &str, limit: usize) -> Result<Vec<NodeData>> {
        let conn = self.conn.lock().unwrap();

        let sql = r#"
            SELECT
                n.UUID,
                n.Metadata,
                n.parent_uuid
            FROM node_table n
            WHERE n.Metadata LIKE ?1
            ORDER BY n.last_modified DESC
            LIMIT ?2
        "#;

        let query_pattern = format!("%{}%", query);
        let mut stmt = conn.prepare(sql)?;

        let nodes = stmt.query_map(params![query_pattern, limit], |row| {
            Ok(NodeData {
                node_uuid: row.get(0)?,
                metadata: row.get(1)?,
                parent_uuid: row.get(2)?,
                data_entries: vec![],
            })
        })?;

        let mut results = Vec::new();
        for node_result in nodes {
            if let Ok(mut node) = node_result {
                // Fetch data entries for this node
                node.data_entries = self.get_data_entries_internal(&conn, &node.node_uuid)?;
                results.push(node);
            }
        }

        Ok(results)
    }

    /// Get context for an app by searching for relevant nodes
    /// This is used when building prompts for the LLM
    pub fn get_context_for_app(&self, app_name: &str, text_buffer: &str, limit: usize) -> Result<Vec<NodeData>> {
        // Combine app name and text buffer for search
        let query = format!("{} {}", app_name, text_buffer);
        self.search_nodes(&query, limit)
    }

    /// Get all recent nodes (for when no specific context found)
    pub fn get_recent_nodes(&self, limit: usize) -> Result<Vec<NodeData>> {
        let conn = self.conn.lock().unwrap();

        let sql = r#"
            SELECT
                n.UUID,
                n.Metadata,
                n.parent_uuid
            FROM node_table n
            ORDER BY n.last_modified DESC
            LIMIT ?1
        "#;

        let mut stmt = conn.prepare(sql)?;

        let nodes = stmt.query_map(params![limit], |row| {
            Ok(NodeData {
                node_uuid: row.get(0)?,
                metadata: row.get(1)?,
                parent_uuid: row.get(2)?,
                data_entries: vec![],
            })
        })?;

        let mut results = Vec::new();
        for node_result in nodes {
            if let Ok(mut node) = node_result {
                node.data_entries = self.get_data_entries_internal(&conn, &node.node_uuid)?;
                results.push(node);
            }
        }

        Ok(results)
    }

    /// Get parent metadata chain for a node (for hierarchical context)
    pub fn get_parent_chain(&self, node_uuid: &str, max_depth: usize) -> Result<Vec<String>> {
        let conn = self.conn.lock().unwrap();
        let mut chain = Vec::new();
        let mut current_uuid = Some(node_uuid.to_string());
        let mut depth = 0;

        while let Some(uuid) = current_uuid {
            if depth >= max_depth {
                break;
            }

            let sql = "SELECT Metadata, parent_uuid FROM node_table WHERE UUID = ?1";
            let mut stmt = conn.prepare(sql)?;

            match stmt.query_row(params![uuid], |row| {
                Ok((row.get::<_, String>(0)?, row.get::<_, Option<String>>(1)?))
            }) {
                Ok((metadata, parent)) => {
                    chain.push(metadata);
                    current_uuid = parent;
                    depth += 1;
                }
                Err(_) => break,
            }
        }

        Ok(chain)
    }

    /// Internal helper to get data entries (used when connection is already locked)
    fn get_data_entries_internal(&self, conn: &Connection, node_uuid: &str) -> Result<Vec<DataEntry>> {
        let sql = r#"
            SELECT key, type, info
            FROM data_table
            WHERE Node_UUID = ?1
            LIMIT 10
        "#;

        let mut stmt = conn.prepare(sql)?;

        let entries = stmt.query_map(params![node_uuid], |row| {
            Ok(DataEntry {
                key: row.get(0)?,
                data_type: row.get(1)?,
                info: row.get(2)?,
            })
        })?;

        let mut results = Vec::new();
        for entry_result in entries {
            if let Ok(entry) = entry_result {
                results.push(entry);
            }
        }

        Ok(results)
    }

    /// Get statistics about the graph (useful for debugging)
    pub fn get_stats(&self) -> Result<GraphStats> {
        let conn = self.conn.lock().unwrap();

        let node_count: i64 = conn.query_row("SELECT COUNT(*) FROM node_table", [], |row| row.get(0))?;
        let data_count: i64 = conn.query_row("SELECT COUNT(*) FROM data_table", [], |row| row.get(0))?;
        let action_count: i64 = conn.query_row("SELECT COUNT(*) FROM action_table", [], |row| row.get(0))?;

        Ok(GraphStats {
            node_count: node_count as usize,
            data_count: data_count as usize,
            action_count: action_count as usize,
        })
    }
}

#[derive(Debug)]
pub struct GraphStats {
    pub node_count: usize,
    pub data_count: usize,
    pub action_count: usize,
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_graph_db_connection() {
        // Test with in-memory database
        let db = GraphDatabase::new(":memory:".to_string());
        assert!(db.is_ok());
    }

    #[test]
    fn test_search_nodes_empty_db() {
        let db = GraphDatabase::new(":memory:".to_string()).unwrap();
        let results = db.search_nodes("test", 10);
        // Empty database should return empty results, not error
        assert!(results.is_ok());
        assert_eq!(results.unwrap().len(), 0);
    }
}
