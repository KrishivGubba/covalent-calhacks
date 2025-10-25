use rusqlite::{params, Connection, Result};
pub const SCHEMA_VERSION: i32 = 1;

pub fn create_tables(conn: &Connection) -> Result<()> {
    create_node_table(conn)?;
    create_data_table(conn)?;
    create_action_table(conn)?;
    ensure_schema_version_table(conn)?;
    Ok(())
}

pub fn create_node_table(conn: &Connection) -> Result<()> {
    conn.execute(
        "CREATE TABLE IF NOT EXISTS node_table (
            node_uuid TEXT PRIMARY KEY NOT NULL,
            metadata TEXT,
            tree_level INTEGER,
            confidence REAL,
            creation_timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            last_edit_timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            parent_uuid TEXT,
            children_uuids TEXT,
            terminal BOOLEAN DEFAULT FALSE,
            data_uuid TEXT NOT NULL,
            action_uuid TEXT,
            FOREIGN KEY (parent_uuid) REFERENCES node_table(node_uuid) ON DELETE SET NULL,
            FOREIGN KEY (data_uuid) REFERENCES data_table(data_uuid),
            FOREIGN KEY (action_uuid) REFERENCES action_table(action_uuid)
        )",
        [],
    )?;
    Ok(())
}

pub fn create_data_table(conn: &Connection) -> Result<()> {
    conn.execute(
        "CREATE TABLE IF NOT EXISTS data_table (
            data_uuid TEXT PRIMARY KEY NOT NULL,
            data_type TEXT,
            data TEXT,
            creation_timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            last_edit_timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            node_uuid TEXT NOT NULL,
            FOREIGN KEY (node_uuid) REFERENCES node_table(node_uuid) ON DELETE CASCADE
        )",
        [],
    )?;
    Ok(())
}

pub fn create_action_table(conn: &Connection) -> Result<()> {
    conn.execute(
        "CREATE TABLE IF NOT EXISTS action_table (
            action_uuid TEXT PRIMARY KEY NOT NULL,
            action_type TEXT,
            action_data TEXT,
            creation_timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            last_edit_timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            node_uuid TEXT NOT NULL,
            data_uuid TEXT NOT NULL,
            FOREIGN KEY (node_uuid) REFERENCES node_table(node_uuid) ON DELETE CASCADE,
            FOREIGN KEY (data_uuid) REFERENCES data_table(data_uuid)
        )",
        [],
    )?;
    Ok(())
}

pub fn ensure_schema_version_table(conn: &Connection) -> Result<()> {
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_version (
            version INTEGER NOT NULL,
            applied_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )",
        [],
    )?;

    let current_max: i32 = conn
        .query_row("SELECT COALESCE(MAX(version), 0) FROM schema_version", [], |row| row.get(0))
        .unwrap_or(0);

    if current_max < SCHEMA_VERSION {
        conn.execute(
            "INSERT INTO schema_version (version) VALUES (?)",
            params![SCHEMA_VERSION],
        )?;
    }

    Ok(())
}
