"""
Database initialization script for Covalent.

Creates an encrypted SQLite database using SQLCipher.
Encryption key is stored in macOS Keychain.

Usage:
    python init_db.py [--db-path path/to/database.db]
"""
import argparse
import os
import sys
from pathlib import Path

_project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_project_root))
from logger import get_logger
log = get_logger()

# Use SQLCipher for encrypted database
try:
    from sqlcipher3 import dbapi2 as sqlite3
except ImportError:
    try:
        from pysqlcipher3 import dbapi2 as sqlite3
    except ImportError:
        raise ImportError(
            "SQLCipher not found. Install with: pip install sqlcipher3-wheels  "
            "(macOS/Windows). Linux: pip install pysqlcipher3-binary. "
            "Or with Homebrew: brew install sqlcipher && pip install pysqlcipher3"
        )

from security.key_manager import get_db_encryption_key


def create_schema(conn: sqlite3.Connection) -> None:
    conn.execute("PRAGMA foreign_keys = ON;")

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS node_table (
            UUID TEXT PRIMARY KEY,
            Metadata TEXT,
            created TEXT,
            last_modified TEXT,
            parent_uuid TEXT,
            children_uuid_arr TEXT,
            embedding BLOB,
            FOREIGN KEY (parent_uuid) REFERENCES node_table(UUID) ON DELETE SET NULL
        );
        """
    )
    
    # Migration: add embedding column if it doesn't exist (for existing databases)
    try:
        conn.execute("ALTER TABLE node_table ADD COLUMN embedding BLOB")
    except Exception:
        pass  # Column already exists

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS action_table (
            UUID TEXT PRIMARY KEY,
            Action_name TEXT,
            Action_plan TEXT,
            Node_UUID TEXT NOT NULL,
            last_selected TEXT,
            FOREIGN KEY (Node_UUID) REFERENCES node_table(UUID) ON DELETE CASCADE
        );
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS data_table (
            UUID TEXT PRIMARY KEY,
            Node_UUID TEXT NOT NULL,
            key TEXT,
            type TEXT,
            info TEXT,
            category TEXT,
            FOREIGN KEY (Node_UUID) REFERENCES node_table(UUID) ON DELETE CASCADE
        );
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS node_counters (
            node_uuid TEXT PRIMARY KEY,
            insertion_count INTEGER DEFAULT 0,
            last_cleanup TEXT,
            FOREIGN KEY (node_uuid) REFERENCES node_table(UUID) ON DELETE CASCADE
        );
        """
    )

    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_action_node_uuid ON action_table (Node_UUID);
        """
    )

    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_data_node_uuid ON data_table (Node_UUID);
        """
    )

    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_action_last_selected ON action_table (last_selected);
        """
    )

    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_data_category ON data_table (category);
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS large_context_sync_config (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            enabled INTEGER NOT NULL DEFAULT 1,
            interval_minutes INTEGER NOT NULL DEFAULT 60,
            projection_mode TEXT NOT NULL DEFAULT 'provider_subtree',
            markdown_root TEXT,
            last_scheduler_heartbeat TEXT
        );
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS large_context_provider_state (
            provider TEXT PRIMARY KEY,
            supports_live_sync INTEGER NOT NULL,
            cursor_json TEXT,
            last_started_at TEXT,
            last_completed_at TEXT,
            last_success_at TEXT,
            last_error TEXT,
            status TEXT,
            last_snapshot_path TEXT
        );
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS large_context_integration_controls (
            integration_id TEXT PRIMARY KEY,
            enabled INTEGER NOT NULL DEFAULT 1,
            interval_minutes INTEGER NOT NULL DEFAULT 60,
            status TEXT NOT NULL DEFAULT 'idle',
            last_started_at TEXT,
            last_completed_at TEXT,
            last_success_at TEXT,
            last_error TEXT
        );
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS large_context_sync_runs (
            run_id TEXT PRIMARY KEY,
            started_at TEXT NOT NULL,
            completed_at TEXT,
            status TEXT NOT NULL,
            providers_attempted TEXT,
            providers_succeeded TEXT,
            providers_failed TEXT,
            error_json TEXT,
            metrics_json TEXT
        );
        """
    )

    try:
        conn.execute("ALTER TABLE large_context_sync_runs ADD COLUMN metrics_json TEXT")
    except Exception:
        pass

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS large_context_entity_state (
            provider_id TEXT NOT NULL,
            entity_type TEXT NOT NULL,
            external_id TEXT NOT NULL,
            container_id TEXT,
            title TEXT,
            source_url TEXT,
            source_updated_at TEXT,
            first_seen_at TEXT NOT NULL,
            last_seen_at TEXT NOT NULL,
            last_changed_at TEXT NOT NULL,
            fingerprint TEXT NOT NULL,
            normalized_json TEXT NOT NULL,
            durable_node_uuid TEXT,
            active_node_uuid TEXT,
            is_active INTEGER NOT NULL DEFAULT 0,
            active_score REAL NOT NULL DEFAULT 0,
            active_reasons_json TEXT NOT NULL DEFAULT '[]',
            last_active_at TEXT,
            PRIMARY KEY (provider_id, entity_type, external_id)
        );
        """
    )

    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_large_context_entity_seen
        ON large_context_entity_state (provider_id, last_seen_at);
        """
    )

    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_large_context_entity_active
        ON large_context_entity_state (provider_id, is_active, active_score);
        """
    )

    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_large_context_entity_updated
        ON large_context_entity_state (provider_id, source_updated_at);
        """
    )

    conn.execute(
        """
        INSERT OR IGNORE INTO large_context_sync_config
            (id, enabled, interval_minutes, projection_mode, markdown_root, last_scheduler_heartbeat)
        VALUES (1, 1, 60, 'provider_subtree', NULL, NULL);
        """
    )

    # OAuth callback polling: state -> code_verifier, tokens, etc. for frontend to pick up
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS auth_pending (
            state TEXT PRIMARY KEY,
            code_verifier TEXT,
            code TEXT,
            access_token TEXT,
            id_token TEXT,
            refresh_token TEXT,
            user_info TEXT,
            error TEXT,
            error_description TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        );
        """
    )

    # Persistent user sessions - survives app restarts
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS user_sessions (
            user_id TEXT PRIMARY KEY,
            access_token TEXT NOT NULL,
            refresh_token TEXT,
            id_token TEXT,
            expires_at TEXT,
            user_info TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        );
        """
    )

    # Integration tokens - OAuth tokens for third-party services (Google, GitHub, Notion)
    # Single-user desktop app, so provider is the primary key (one token per provider)
    # To check if integration is connected: SELECT 1 FROM integration_tokens WHERE provider=?
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS integration_tokens (
            provider TEXT PRIMARY KEY,
            access_token TEXT NOT NULL,
            refresh_token TEXT,
            expires_at TEXT,
            scopes TEXT,
            provider_metadata TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        );
        """
    )

    # Seed built-in integrations that don't require OAuth (always "connected")
    conn.execute(
        """
        INSERT OR IGNORE INTO integration_tokens (provider, access_token, scopes, provider_metadata)
        VALUES ('perplexity', 'api-key-based', 'search', '{"type": "api_key"}');
        """
    )

    # Action execution history - tracks all executed actions for history page
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS action_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            action_uuid TEXT NOT NULL,
            action_type TEXT NOT NULL,
            action_data TEXT,
            creation_timestamp TEXT DEFAULT (datetime('now')),
            node_uuid TEXT,
            status TEXT DEFAULT 'completed',
            result TEXT,
            error_message TEXT,
            duration_ms INTEGER,
            FOREIGN KEY (node_uuid) REFERENCES node_table(UUID) ON DELETE SET NULL
        );
        """
    )

    # Indexes for action_history queries
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_action_history_timestamp ON action_history(creation_timestamp);
        """
    )

    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_action_history_type ON action_history(action_type);
        """
    )

    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_action_history_status ON action_history(status);
        """
    )

    conn.commit()


def ensure_parent_dir(path: str) -> None:
    parent = os.path.dirname(os.path.abspath(path))
    if parent and not os.path.exists(parent):
        os.makedirs(parent, exist_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Initialize encrypted SQLite database for Covalent"
    )
    parser.add_argument(
        "--db-path",
        default=os.path.join(os.path.dirname(__file__), "graph.db"),
        help="Path to the database file (default: context-engine/graph.db)"
    )
    args = parser.parse_args()

    ensure_parent_dir(args.db_path)
    
    # Check if database already exists
    db_exists = os.path.exists(args.db_path)
    if db_exists:
        log.warning(f"⚠️  Database already exists at: {args.db_path}")
        log.info("   To create a fresh database, delete the existing one first.")
    
    # Get encryption key from Keychain (creates one if doesn't exist)
    log.info("🔑 Retrieving encryption key from Keychain...")
    key = get_db_encryption_key()
    
    # Create encrypted database connection
    conn = sqlite3.connect(args.db_path)
    
    # CRITICAL: Set encryption key BEFORE any other operations
    conn.execute(f"PRAGMA key = '{key}'")
    
    # Create schema
    create_schema(conn)
    conn.close()
    
    # Set secure file permissions (owner read/write only)
    os.chmod(args.db_path, 0o600)
    
    log.info(f"✅ Initialized encrypted SQLite database at: {args.db_path}")
    log.info(f"🔒 Database is encrypted with SQLCipher (AES-256)")
    log.info(f"🔑 Encryption key stored in macOS Keychain")
    log.info(f"📁 File permissions set to 0o600 (owner read/write only)")


if __name__ == "__main__":
    main()
