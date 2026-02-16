"""
Data Access Object for Integration operations.
Handles OAuth tokens for third-party integrations (Google, GitHub, Notion).
Single-user desktop app - no user_id needed.

Database is encrypted using SQLCipher. Encryption key is stored in macOS Keychain.
"""
import os
import sys
import json
from typing import Optional, Dict, Any, List

# Use SQLCipher for encrypted database access
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

# Add context-engine to path for security module access
_context_engine_path = os.path.join(os.path.dirname(__file__), '..', 'context-engine')
if _context_engine_path not in sys.path:
    sys.path.insert(0, _context_engine_path)

from security.key_manager import get_db_encryption_key


# Known integration providers
PROVIDERS = ["google", "github", "notion", "filesystem"]


class IntegrationDAO:
    """DAO for integration-related database operations."""

    def __init__(self, db_path: str):
        self.db_path = db_path
        # Set secure file permissions on database if it exists
        if os.path.exists(db_path):
            os.chmod(db_path, 0o600)

    def _conn(self) -> sqlite3.Connection:
        """Create a new encrypted connection (short-lived for thread safety)."""
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        # Set encryption key before any other operations
        key = get_db_encryption_key()
        conn.execute(f"PRAGMA key = '{key}'")
        return conn

    def ensure_table(self) -> None:
        """Create integration_tokens table if it doesn't exist, and seed default integrations."""
        conn = self._conn()
        try:
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
                )
                """
            )
            
            # Seed built-in integrations that don't require OAuth
            # These are always "connected" - filesystem uses local access, perplexity uses API key
            builtin_integrations = [
                ("filesystem", "built-in", None, None, "local", '{"type": "local_filesystem"}'),
                ("perplexity", "api-key-based", None, None, "search", '{"type": "api_key"}'),
            ]
            for provider, access_token, refresh_token, expires_at, scopes, metadata in builtin_integrations:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO integration_tokens 
                        (provider, access_token, refresh_token, expires_at, scopes, provider_metadata)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (provider, access_token, refresh_token, expires_at, scopes, metadata),
                )
            
            conn.commit()
        finally:
            conn.close()

    # --- Status Checks ---

    def is_connected(self, provider: str) -> bool:
        """Check if a specific integration is connected."""
        conn = self._conn()
        try:
            row = conn.execute(
                "SELECT 1 FROM integration_tokens WHERE provider = ?",
                (provider,),
            ).fetchone()
            return row is not None
        finally:
            conn.close()

    def get_all_statuses(self) -> Dict[str, bool]:
        """Get connection status for all known providers."""
        conn = self._conn()
        try:
            rows = conn.execute(
                "SELECT provider FROM integration_tokens"
            ).fetchall()
            connected_providers = {row[0] for row in rows}
            return {provider: provider in connected_providers for provider in PROVIDERS}
        finally:
            conn.close()

    # --- Token Operations ---

    def save_token(
        self,
        provider: str,
        access_token: str,
        refresh_token: Optional[str] = None,
        expires_at: Optional[str] = None,
        scopes: Optional[str] = None,
        provider_metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Save or update integration tokens."""
        metadata_json = json.dumps(provider_metadata) if provider_metadata else None
        conn = self._conn()
        try:
            conn.execute(
                """
                INSERT INTO integration_tokens 
                    (provider, access_token, refresh_token, expires_at, scopes, provider_metadata, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
                ON CONFLICT(provider) DO UPDATE SET
                    access_token = excluded.access_token,
                    refresh_token = COALESCE(excluded.refresh_token, refresh_token),
                    expires_at = excluded.expires_at,
                    scopes = COALESCE(excluded.scopes, scopes),
                    provider_metadata = COALESCE(excluded.provider_metadata, provider_metadata),
                    updated_at = datetime('now')
                """,
                (provider, access_token, refresh_token, expires_at, scopes, metadata_json),
            )
            conn.commit()
        finally:
            conn.close()

    def get_token(self, provider: str) -> Optional[Dict[str, Any]]:
        """Get integration tokens for a provider."""
        conn = self._conn()
        try:
            row = conn.execute(
                """SELECT access_token, refresh_token, expires_at, scopes, provider_metadata, created_at, updated_at
                   FROM integration_tokens WHERE provider = ?""",
                (provider,),
            ).fetchone()
            if not row:
                return None
            return {
                "provider": provider,
                "access_token": row[0],
                "refresh_token": row[1],
                "expires_at": row[2],
                "scopes": row[3],
                "provider_metadata": json.loads(row[4]) if row[4] else None,
                "created_at": row[5],
                "updated_at": row[6],
            }
        finally:
            conn.close()

    def update_access_token(self, provider: str, access_token: str, expires_at: Optional[str] = None) -> int:
        """Update just the access token (after refresh)."""
        conn = self._conn()
        try:
            cursor = conn.execute(
                "UPDATE integration_tokens SET access_token = ?, expires_at = ?, updated_at = datetime('now') WHERE provider = ?",
                (access_token, expires_at, provider),
            )
            conn.commit()
            return cursor.rowcount
        finally:
            conn.close()

    def delete_token(self, provider: str) -> int:
        """Delete integration (disconnect)."""
        conn = self._conn()
        try:
            cursor = conn.execute(
                "DELETE FROM integration_tokens WHERE provider = ?",
                (provider,),
            )
            conn.commit()
            return cursor.rowcount
        finally:
            conn.close()

    def get_all_tokens(self) -> List[Dict[str, Any]]:
        """Get all integration tokens."""
        conn = self._conn()
        try:
            rows = conn.execute(
                """SELECT provider, access_token, refresh_token, expires_at, scopes, provider_metadata, updated_at
                   FROM integration_tokens"""
            ).fetchall()
            return [
                {
                    "provider": row[0],
                    "access_token": row[1],
                    "refresh_token": row[2],
                    "expires_at": row[3],
                    "scopes": row[4],
                    "provider_metadata": json.loads(row[5]) if row[5] else None,
                    "updated_at": row[6],
                }
                for row in rows
            ]
        finally:
            conn.close()
