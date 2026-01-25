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
            Action_prompt TEXT,
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
