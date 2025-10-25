// vibecoded slop, will fix and clean later

use std::sync::{Arc, Mutex};
use std::path::PathBuf;
use rusqlite::{Connection, Result as SqliteResult};
use anyhow::{Result, Context};
use crate::database::schema_sql::{create_tables, SCHEMA_VERSION};

pub struct DatabaseManager {
    connection: Arc<Mutex<Connection>>,
    db_path: PathBuf,
}

impl DatabaseManager {
    pub fn new() -> Result<Self> {
        let db_path = Self::get_default_database_path()?;
        
        // Ensure the directory exists
        if let Some(parent) = db_path.parent() {
            std::fs::create_dir_all(parent)
                .context("Failed to create database directory")?;
        }

        let connection = Connection::open(&db_path)
            .context("Failed to open database connection")?;

        // Enable foreign key constraints
        connection.execute("PRAGMA foreign_keys = ON", [])
            .context("Failed to enable foreign key constraints")?;

        // Enable WAL mode for better concurrency
        connection.execute("PRAGMA journal_mode = WAL", [])
            .context("Failed to enable WAL mode")?;

        // Optimize SQLite settings
        connection.execute("PRAGMA synchronous = NORMAL", [])
            .context("Failed to set synchronous mode")?;
        
        connection.execute("PRAGMA cache_size = 10000", [])
            .context("Failed to set cache size")?;
        
        connection.execute("PRAGMA temp_store = MEMORY", [])
            .context("Failed to set temp store to memory")?;

        let manager = Self {
            connection: Arc::new(Mutex::new(connection)),
            db_path,
        };

        // Initialize database schema
        manager.initialize_database()?;

        Ok(manager)
    }

    fn get_default_database_path() -> Result<PathBuf> {
        let app_dir = dirs::data_local_dir()
            .context("Failed to get local data directory")?
            .join("covalentai");
        
        Ok(app_dir.join("covalent.db"))
    }

    pub fn initialize_database(&self) -> Result<()> {
        let conn = self.connection.lock().unwrap();
        
        // Check current schema version
        let current_version = self.get_schema_version(&conn)?;
        
        if current_version < SCHEMA_VERSION {
            log::info!("Initializing database schema (version {})", SCHEMA_VERSION);
            create_tables(&conn)
                .context("Failed to create database tables")?;
        }

        Ok(())
    }

    fn get_schema_version(&self, conn: &Connection) -> Result<i32> {
        // Check if schema_version table exists
        let table_exists: bool = conn
            .prepare("SELECT name FROM sqlite_master WHERE type='table' AND name='schema_version'")
            .and_then(|mut stmt| {
                stmt.query_map([], |_| Ok(()))
                    .and_then(|rows| Ok(rows.count() > 0))
            })
            .unwrap_or(false);

        if !table_exists {
            return Ok(0);
        }

        let version: i32 = conn
            .prepare("SELECT MAX(version) FROM schema_version")
            .and_then(|mut stmt| {
                stmt.query_row([], |row| row.get(0))
            })
            .unwrap_or(0);

        Ok(version)
    }

    pub fn with_connection<F, R>(&self, f: F) -> Result<R>
    where
        F: FnOnce(&Connection) -> SqliteResult<R>,
    {
        let conn = self.connection.lock().unwrap();
        f(&conn).context("Database operation failed")
    }

    pub fn execute_transaction<F, R>(&self, f: F) -> Result<R>
    where
        F: FnOnce(&Connection) -> SqliteResult<R>,
    {
        let conn = self.connection.lock().unwrap();
        
        conn.execute("BEGIN TRANSACTION", [])
            .context("Failed to begin transaction")?;

        match f(&conn) {
            Ok(result) => {
                conn.execute("COMMIT", [])
                    .context("Failed to commit transaction")?;
                Ok(result)
            }
            Err(e) => {
                conn.execute("ROLLBACK", [])
                    .context("Failed to rollback transaction")?;
                Err(anyhow::Error::new(e))
            }
        }
    }

    pub fn backup_database(&self, backup_path: &PathBuf) -> Result<()> {
        // Create backup directory if it doesn't exist
        if let Some(parent) = backup_path.parent() {
            std::fs::create_dir_all(parent)
                .context("Failed to create backup directory")?;
        }

        // Simple file copy backup
        std::fs::copy(&self.db_path, backup_path)
            .context("Failed to copy database file")?;

        log::info!("Database backed up to: {:?}", backup_path);
        Ok(())
    }

    pub fn get_database_path(&self) -> &PathBuf {
        &self.db_path
    }

    pub fn get_database_stats(&self) -> Result<DatabaseStats> {
        self.with_connection(|conn| {
            let mut stats = DatabaseStats::default();

            // Get table counts
            stats.user_profiles = conn.prepare("SELECT COUNT(*) FROM user_profiles")?
                .query_row([], |row| row.get(0))?;
            
            stats.personas = conn.prepare("SELECT COUNT(*) FROM personas")?
                .query_row([], |row| row.get(0))?;
            
            stats.context_sessions = conn.prepare("SELECT COUNT(*) FROM context_sessions")?
                .query_row([], |row| row.get(0))?;
            
            stats.conversations = conn.prepare("SELECT COUNT(*) FROM conversations")?
                .query_row([], |row| row.get(0))?;
            
            stats.messages = conn.prepare("SELECT COUNT(*) FROM messages")?
                .query_row([], |row| row.get(0))?;
            
            stats.knowledge_entries = conn.prepare("SELECT COUNT(*) FROM knowledge_entries")?
                .query_row([], |row| row.get(0))?;
            
            stats.documents = conn.prepare("SELECT COUNT(*) FROM documents")?
                .query_row([], |row| row.get(0))?;

            // Get database file size
            let db_size_pages: i64 = conn.prepare("PRAGMA page_count")?
                .query_row([], |row| row.get(0))?;
            
            let page_size: i64 = conn.prepare("PRAGMA page_size")?
                .query_row([], |row| row.get(0))?;
            
            stats.database_size_bytes = db_size_pages * page_size;

            Ok(stats)
        })
    }

    pub fn vacuum_database(&self) -> Result<()> {
        self.with_connection(|conn| {
            conn.execute("VACUUM", [])?;
            Ok(())
        })
    }

    pub fn analyze_database(&self) -> Result<()> {
        self.with_connection(|conn| {
            conn.execute("ANALYZE", [])?;
            Ok(())
        })
    }
}

#[derive(Debug, Default, serde::Serialize)]
pub struct DatabaseStats {
    pub user_profiles: i64,
    pub personas: i64,
    pub context_sessions: i64,
    pub conversations: i64,
    pub messages: i64,
    pub knowledge_entries: i64,
    pub documents: i64,
    pub database_size_bytes: i64,
}

impl Clone for DatabaseManager {
    fn clone(&self) -> Self {
        Self {
            connection: Arc::clone(&self.connection),
            db_path: self.db_path.clone(),
        }
    }
}