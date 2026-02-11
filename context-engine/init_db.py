import argparse
import os
import sqlite3


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
            FOREIGN KEY (parent_uuid) REFERENCES node_table(UUID) ON DELETE SET NULL
        );
        """
    )

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
        VALUES ('filesystem', 'built-in', 'local', '{"type": "local_filesystem"}'),
               ('perplexity', 'api-key-based', 'search', '{"type": "api_key"}');
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
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--db-path",
        default=os.path.join(os.path.dirname(__file__), "graph.db"),
    )
    args = parser.parse_args()

    ensure_parent_dir(args.db_path)

    with sqlite3.connect(args.db_path) as conn:
        create_schema(conn)

    print(f"Initialized SQLite database at: {args.db_path}")


if __name__ == "__main__":
    main()
