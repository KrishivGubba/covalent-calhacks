"""
Filesystem MCP Tools & Resources - Local file and directory operations.

Write operations (tools): write_file, create_directory, delete_path, move_path, copy_path
Read operations (resources): read_file, list_directory, file_exists, grep, read_pdf

All operations are scoped to a user-chosen root directory persisted in the database.
Raises RuntimeError if the user hasn't connected a folder yet.
"""
import json
import os
import sys
from pathlib import Path
from typing import Dict, Optional

# Use SQLCipher for encrypted database access (same as integration_dao / graph_dao)
try:
    from sqlcipher3 import dbapi2 as sqlite3
except ImportError:
    try:
        from pysqlcipher3 import dbapi2 as sqlite3
    except ImportError:
        import sqlite3  # type: ignore[no-redef]

# Add context-engine to path so we can import the key manager
_context_engine_path = str(Path(__file__).resolve().parent.parent.parent.parent / "context-engine")
if _context_engine_path not in sys.path:
    sys.path.insert(0, _context_engine_path)

from covalent_mcp.toolclasses.base import (
    MCPToolModule,
    ToolDisplaySchema,
    DisplayField,
)
from covalent_mcp.toolclasses.filesystem.filesystem_client import FilesystemClient
from fastmcp import FastMCP


def _get_filesystem_root_from_db() -> Optional[str]:
    """Read the filesystem root path from the integration_tokens table in graph.db."""
    # Use GRAPH_DB_PATH env var if set, otherwise fall back to context-engine/graph.db
    project_root = Path(__file__).resolve().parent.parent.parent.parent
    db_path = Path(os.environ.get("GRAPH_DB_PATH", str(project_root / "context-engine" / "graph.db")))
    if not db_path.exists():
        return None
    try:
        conn = sqlite3.connect(str(db_path), timeout=5.0)
        # Set encryption key if using SQLCipher
        try:
            from security.key_manager import get_db_encryption_key
            key = get_db_encryption_key()
            conn.execute(f"PRAGMA key = '{key}'")
        except ImportError:
            pass  # No SQLCipher / key_manager available — DB is unencrypted
        row = conn.execute(
            "SELECT provider_metadata FROM integration_tokens WHERE provider = 'filesystem'"
        ).fetchone()
        conn.close()
        if row and row[0]:
            metadata = json.loads(row[0])
            root = metadata.get("root_path")
            if root and os.path.isdir(root):
                return root
    except Exception:
        pass
    return None


class FilesystemToolModule(MCPToolModule):
    """
    Filesystem module for local file and directory operations.

    Provides MCP tools (write operations) for:
    - Writing text files
    - Creating directories
    - Deleting files and directories
    - Moving and copying paths

    Provides MCP resources (read-only operations) for:
    - Reading text files
    - Listing directories
    - Checking if a path exists
    - Grep-style search
    - PDF text extraction
    """

    def __init__(self) -> None:
        self._client: Optional[FilesystemClient] = None
        self._client_root: Optional[str] = None  # Track which root the client was created with

    def _ensure_client(self) -> FilesystemClient:
        """
        Get or create the filesystem client.
        Re-creates the client if the configured root has changed (e.g. user
        connected a new folder via the UI).

        Raises:
            RuntimeError: If no filesystem root has been configured (user must
                          pick a folder via the Integrations page first).
        """
        current_root = _get_filesystem_root_from_db()

        if not current_root:
            raise RuntimeError(
                "Filesystem not connected. Please choose a folder in the Integrations page first."
            )

        if self._client is not None and self._client_root == current_root:
            return self._client

        # Root changed (or first init) -- create new client
        self._client = FilesystemClient(root=current_root)
        self._client_root = current_root
        print(f"📁 FilesystemClient initialized with root: {self._client.root}")
        return self._client

    def get_display_schemas(self) -> Dict[str, ToolDisplaySchema]:
        """Return display schemas for filesystem tools (write ops only)."""
        return {
            "write_file": ToolDisplaySchema(
                tool_name="write_file",
                display_name="Write File",
                description="Write content to a local text file.",
                fields=[
                    DisplayField(key="path", label="File Path", required=True, widget="text_input"),
                    DisplayField(key="content", label="Content", required=True, widget="textarea"),
                    DisplayField(key="create_dirs", label="Create Parent Dirs", widget="toggle"),
                ],
            ),
            "create_directory": ToolDisplaySchema(
                tool_name="create_directory",
                display_name="Create Directory",
                description="Create a new directory.",
                fields=[
                    DisplayField(key="path", label="Directory Path", required=True, widget="text_input"),
                    DisplayField(key="parents", label="Create Parents", widget="toggle"),
                ],
            ),
            "delete_path": ToolDisplaySchema(
                tool_name="delete_path",
                display_name="Delete Path",
                description="Delete a file or directory.",
                fields=[
                    DisplayField(key="path", label="Path", required=True, widget="text_input"),
                    DisplayField(key="recursive", label="Recursive", widget="toggle"),
                ],
            ),
            "move_path": ToolDisplaySchema(
                tool_name="move_path",
                display_name="Move / Rename Path",
                description="Move or rename a file or directory.",
                fields=[
                    DisplayField(key="src", label="Source Path", required=True, widget="text_input"),
                    DisplayField(key="dst", label="Destination Path", required=True, widget="text_input"),
                ],
            ),
            "copy_path": ToolDisplaySchema(
                tool_name="copy_path",
                display_name="Copy Path",
                description="Copy a file or directory.",
                fields=[
                    DisplayField(key="src", label="Source Path", required=True, widget="text_input"),
                    DisplayField(key="dst", label="Destination Path", required=True, widget="text_input"),
                ],
            ),
        }

    def register(self, mcp: FastMCP) -> None:
        """Register filesystem tools (write operations) with the MCP server."""
        module = self

        @mcp.tool()
        def write_file(
            path: str,
            content: str,
            encoding: str = "utf-8",
            create_dirs: bool = True,
        ) -> dict:
            """
            Write content to a text file. Creates parent directories if create_dirs is True.

            Args:
                path: Path relative to the filesystem root
                content: File content
                encoding: Text encoding (default: utf-8)
                create_dirs: Create parent directories if missing (default: True)

            Returns:
                Dict with success and message (or error).
            """
            client = module._ensure_client()
            ok = client.write_file(path, content, encoding=encoding, create_dirs=create_dirs)
            if not ok:
                return {"success": False, "error": "Write failed (path invalid or outside root)"}
            return {"success": True, "message": f"Wrote {path}"}

        @mcp.tool()
        def create_directory(path: str, parents: bool = True) -> dict:
            """
            Create a directory. Creates parent directories if parents is True.

            Args:
                path: Directory path relative to root
                parents: Create parent directories if missing (default: True)

            Returns:
                Dict with success and message (or error).
            """
            client = module._ensure_client()
            ok = client.create_directory(path, parents=parents)
            if not ok:
                return {"success": False, "error": "Create failed (path invalid or outside root)"}
            return {"success": True, "message": f"Created directory {path}"}

        @mcp.tool()
        def delete_path(path: str, recursive: bool = False) -> dict:
            """
            Delete a file or directory. Directories must be empty unless recursive is True.

            Args:
                path: Path relative to root
                recursive: If True, delete non-empty directories (default: False)

            Returns:
                Dict with success and message (or error).
            """
            client = module._ensure_client()
            ok, err = client.delete_path(path, recursive=recursive)
            if not ok:
                return {"success": False, "error": err or "Delete failed"}
            return {"success": True, "message": f"Deleted {path}"}

        @mcp.tool()
        def move_path(src: str, dst: str) -> dict:
            """
            Move or rename a file or directory.

            Args:
                src: Source path relative to root
                dst: Destination path relative to root

            Returns:
                Dict with success and message (or error).
            """
            client = module._ensure_client()
            ok, err = client.move_path(src, dst)
            if not ok:
                return {"success": False, "error": err or "Move failed"}
            return {"success": True, "message": f"Moved {src} -> {dst}"}

        @mcp.tool()
        def copy_path(src: str, dst: str) -> dict:
            """
            Copy a file or directory.

            Args:
                src: Source path relative to root
                dst: Destination path relative to root

            Returns:
                Dict with success and message (or error).
            """
            client = module._ensure_client()
            ok, err = client.copy_path(src, dst)
            if not ok:
                return {"success": False, "error": err or "Copy failed"}
            return {"success": True, "message": f"Copied {src} -> {dst}"}

    def register_resources(self, mcp: FastMCP) -> None:
        """Register filesystem resources (read-only operations) with the MCP server."""
        module = self

        @mcp.resource("fs://read_file{?path,encoding}")
        def read_file(path: str = "", encoding: str = "utf-8") -> str:
            """
            Read the contents of a text file.

            URI: fs://read_file{?path,encoding}

            Args:
                path: Path relative to the filesystem root (e.g. "foo/bar.txt")
                encoding: Text encoding (default: utf-8)

            Returns:
                JSON string with success and content (or error message).
            """
            client = module._ensure_client()
            content = client.read_file(path, encoding=encoding)
            if content is None:
                return json.dumps({"success": False, "error": "File not found or outside allowed root", "content": ""})
            return json.dumps({"success": True, "content": content})

        @mcp.resource("fs://list_directory{?path}")
        def list_directory(path: str = ".") -> str:
            """
            List contents of a directory.

            URI: fs://list_directory{?path}

            Args:
                path: Directory path relative to root (default: "." for root)

            Returns:
                JSON string with success and entries (list of {name, path, is_dir}).
            """
            client = module._ensure_client()
            entries = client.list_directory(path)
            if entries is None:
                return json.dumps({"success": False, "error": "Directory not found or outside allowed root", "entries": []})
            return json.dumps({"success": True, "entries": entries})

        @mcp.resource("fs://file_exists{?path}")
        def file_exists(path: str = "") -> str:
            """
            Check if a path exists (file or directory).

            URI: fs://file_exists{?path}

            Args:
                path: Path relative to root

            Returns:
                JSON string with success and exists (bool).
            """
            client = module._ensure_client()
            exists = client.file_exists(path)
            return json.dumps({"success": True, "exists": exists})

        @mcp.resource("fs://grep{?path,pattern,max_matches,recursive,use_regex,encoding}")
        def grep(
            path: str = ".",
            pattern: str = "",
            max_matches: int = 25,
            recursive: bool = True,
            use_regex: bool = False,
            encoding: str = "utf-8",
        ) -> str:
            """
            Search directory for pattern in file contents (grep-style).

            URI: fs://grep{?path,pattern,max_matches,recursive,use_regex,encoding}

            Args:
                path: Directory path relative to root to search in
                pattern: String to search for (substring or regex if use_regex)
                max_matches: Maximum number of matches to return (default: 25)
                recursive: Search subdirectories (default: True)
                use_regex: Treat pattern as regex (default: False)
                encoding: Text encoding for files (default: utf-8)

            Returns:
                JSON string with success, matches, and truncated flag.
            """
            client = module._ensure_client()
            out = client.search_directory(
                path=path,
                pattern=pattern,
                max_matches=max_matches,
                recursive=recursive,
                use_regex=use_regex,
                encoding=encoding,
            )
            if out is None:
                return json.dumps({
                    "success": False,
                    "error": "Directory not found, outside root, or invalid regex",
                    "matches": [],
                    "truncated": False,
                })
            matches, truncated = out
            return json.dumps({"success": True, "matches": matches, "truncated": truncated})

        @mcp.resource("fs://read_pdf{?path}")
        def read_pdf(path: str = "") -> str:
            """
            Extract text from a PDF file.

            URI: fs://read_pdf{?path}

            Args:
                path: PDF path relative to filesystem root

            Returns:
                JSON string with structured PDF extraction (pages, total_pages, etc).
            """
            client = module._ensure_client()
            result = client.read_pdf(path)
            if result is None:
                return json.dumps({
                    "success": False,
                    "error": "File not found, outside root, not a PDF, or extraction failed",
                    "pages": [],
                    "total_pages": 0,
                    "extraction_method": "text",
                    "warnings": [],
                })
            return json.dumps({"success": True, **result})


# Module instance for registry
module = FilesystemToolModule()
