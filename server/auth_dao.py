"""
Data Access Object for Auth operations.
Handles OAuth state, tokens, and user sessions in SQLite.
"""
import sqlite3
import json
from typing import Optional, Dict, Any


class AuthDAO:
    """DAO for auth-related database operations."""

    def __init__(self, db_path: str):
        self.db_path = db_path

    def _conn(self) -> sqlite3.Connection:
        """Create a new connection (short-lived for thread safety)."""
        return sqlite3.connect(self.db_path, timeout=10.0)

    def execute_query(self, query: str, params: tuple = ()) -> list:
        """Execute a query and return results. Auto-commits."""
        conn = self._conn()
        try:
            cursor = conn.execute(query, params)
            conn.commit()
            return cursor.fetchall()
        finally:
            conn.close()

    def execute_update(self, query: str, params: tuple = ()) -> int:
        """Execute an update/insert and return rowcount. Auto-commits."""
        conn = self._conn()
        try:
            cursor = conn.execute(query, params)
            conn.commit()
            return cursor.rowcount
        finally:
            conn.close()

    # --- Auth-specific operations ---

    def save_code_verifier(self, state: str, code_verifier: str) -> None:
        """Store the code_verifier sent by frontend before Auth0 login."""
        self.execute_update(
            "INSERT OR REPLACE INTO auth_pending (state, code_verifier, created_at) VALUES (?, ?, datetime('now'))",
            (state, code_verifier),
        )

    def get_code_verifier(self, state: str) -> Optional[str]:
        """Retrieve code_verifier for a given state."""
        rows = self.execute_query(
            "SELECT code_verifier FROM auth_pending WHERE state = ?",
            (state,),
        )
        return rows[0][0] if rows else None

    def save_auth_result(
        self,
        state: str,
        access_token: Optional[str] = None,
        id_token: Optional[str] = None,
        refresh_token: Optional[str] = None,
        user_info: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
        error_description: Optional[str] = None,
    ) -> None:
        """Store tokens or error after server-side token exchange."""
        user_info_json = json.dumps(user_info) if user_info else None
        self.execute_update(
            """UPDATE auth_pending 
               SET access_token=?, id_token=?, refresh_token=?, user_info=?, error=?, error_description=?
               WHERE state=?""",
            (access_token, id_token, refresh_token, user_info_json, error, error_description, state),
        )

    def get_and_consume_pending_auth(self, state: str) -> Dict[str, Any]:
        """
        Get pending auth for this state and remove it so tokens are only returned once.
        Returns dict: { "status": "pending" | "ready" | "error", tokens/user if ready, error info if error }
        """
        conn = self._conn()
        try:
            row = conn.execute(
                "SELECT access_token, id_token, refresh_token, user_info, error, error_description FROM auth_pending WHERE state = ?",
                (state,),
            ).fetchone()

            if row is None:
                return {"status": "pending"}

            access_token, id_token, refresh_token, user_info, err, err_desc = row

            if err or err_desc:
                conn.execute("DELETE FROM auth_pending WHERE state = ?", (state,))
                conn.commit()
                return {"status": "error", "error": err or "unknown", "error_description": err_desc or ""}

            if access_token:
                conn.execute("DELETE FROM auth_pending WHERE state = ?", (state,))
                conn.commit()
                return {
                    "status": "ready",
                    "access_token": access_token,
                    "id_token": id_token,
                    "refresh_token": refresh_token,
                    "user_info": json.loads(user_info) if user_info else None,
                }

            return {"status": "pending"}
        finally:
            conn.close()

    # --- Persistent Session Operations ---

    def ensure_sessions_table(self) -> None:
        """Create user_sessions table if it doesn't exist (migration)."""
        self.execute_update(
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
            )
            """
        )

    def save_session(
        self,
        user_id: str,
        access_token: str,
        refresh_token: Optional[str] = None,
        id_token: Optional[str] = None,
        expires_at: Optional[str] = None,
        user_info: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Save or update a user session (persists across app restarts)."""
        user_info_json = json.dumps(user_info) if user_info else None
        self.execute_update(
            """
            INSERT INTO user_sessions (user_id, access_token, refresh_token, id_token, expires_at, user_info, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
            ON CONFLICT(user_id) DO UPDATE SET
                access_token = excluded.access_token,
                refresh_token = COALESCE(excluded.refresh_token, refresh_token),
                id_token = excluded.id_token,
                expires_at = excluded.expires_at,
                user_info = COALESCE(excluded.user_info, user_info),
                updated_at = datetime('now')
            """,
            (user_id, access_token, refresh_token, id_token, expires_at, user_info_json),
        )

    def get_session(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a user session by user_id."""
        rows = self.execute_query(
            "SELECT access_token, refresh_token, id_token, expires_at, user_info, created_at, updated_at FROM user_sessions WHERE user_id = ?",
            (user_id,),
        )
        if not rows:
            return None
        access_token, refresh_token, id_token, expires_at, user_info, created_at, updated_at = rows[0]
        return {
            "user_id": user_id,
            "access_token": access_token,
            "refresh_token": refresh_token,
            "id_token": id_token,
            "expires_at": expires_at,
            "user_info": json.loads(user_info) if user_info else None,
            "created_at": created_at,
            "updated_at": updated_at,
        }

    def update_access_token(self, user_id: str, access_token: str, expires_at: str) -> int:
        """Update just the access token and expiry (after refresh)."""
        return self.execute_update(
            "UPDATE user_sessions SET access_token = ?, expires_at = ?, updated_at = datetime('now') WHERE user_id = ?",
            (access_token, expires_at, user_id),
        )

    def delete_session(self, user_id: str) -> int:
        """Delete a user session (logout)."""
        return self.execute_update(
            "DELETE FROM user_sessions WHERE user_id = ?",
            (user_id,),
        )

    def get_all_sessions(self) -> list:
        """Get all active sessions (for debugging/admin)."""
        rows = self.execute_query(
            "SELECT user_id, expires_at, user_info, updated_at FROM user_sessions"
        )
        return [
            {
                "user_id": row[0],
                "expires_at": row[1],
                "user_info": json.loads(row[2]) if row[2] else None,
                "updated_at": row[3],
            }
            for row in rows
        ]
