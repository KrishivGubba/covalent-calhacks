"""
Filesystem MCP Tools - Local file and directory operations.

Exposes filesystem operations as MCP tools for LLM agents.
All operations are scoped to a configurable root (FILESYSTEM_ROOT or cwd).
"""
from typing import Optional

from covalent_mcp.toolclasses.base import MCPToolModule
from covalent_mcp.toolclasses.filesystem.filesystem_client import FilesystemClient
from fastmcp import FastMCP


class FilesystemToolModule(MCPToolModule):
    """
    Filesystem tool module for local file and directory operations.

    Provides MCP tools for:
    - Reading and writing text files
    - Listing directories
    - Creating directories
    - Deleting files and directories (optional recursive)
    - Moving and copying paths
    - Checking if a path exists
    - Grep-style search in directory contents
    - PDF text extraction (structured output)
    """

    def __init__(self) -> None:
        self._client: Optional[FilesystemClient] = None

    def _ensure_client(self) -> FilesystemClient:
        if self._client is None:
            self._client = FilesystemClient()
        return self._client

    def register(self, mcp: FastMCP) -> None:
        """Register filesystem tools with the MCP server."""
        client = self._ensure_client()

        @mcp.tool()
        def read_file(path: str, encoding: str = "utf-8") -> dict:
            """
            Read the contents of a text file.

            Args:
                path: Path relative to the filesystem root (e.g. "foo/bar.txt")
                encoding: Text encoding (default: utf-8)

            Returns:
                Dict with success, content (or error message). Content is empty if failed.
            """
            content = client.read_file(path, encoding=encoding)
            if content is None:
                return {"success": False, "error": "File not found or outside allowed root", "content": ""}
            return {"success": True, "content": content}

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
            ok = client.write_file(path, content, encoding=encoding, create_dirs=create_dirs)
            if not ok:
                return {"success": False, "error": "Write failed (path invalid or outside root)"}
            return {"success": True, "message": f"Wrote {path}"}

        @mcp.tool()
        def list_directory(path: str = ".") -> dict:
            """
            List contents of a directory.

            Args:
                path: Directory path relative to root (default: "." for root)

            Returns:
                Dict with success, entries (list of {name, path, is_dir}), or error.
            """
            entries = client.list_directory(path)
            if entries is None:
                return {"success": False, "error": "Directory not found or outside allowed root", "entries": []}
            return {"success": True, "entries": entries}

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
            ok, err = client.delete_path(path, recursive=recursive)
            if not ok:
                return {"success": False, "error": err or "Delete failed"}
            return {"success": True, "message": f"Deleted {path}"}

        @mcp.tool()
        def file_exists(path: str) -> dict:
            """
            Check if a path exists (file or directory).

            Args:
                path: Path relative to root

            Returns:
                Dict with success and exists (bool).
            """
            exists = client.file_exists(path)
            return {"success": True, "exists": exists}

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
            ok, err = client.copy_path(src, dst)
            if not ok:
                return {"success": False, "error": err or "Copy failed"}
            return {"success": True, "message": f"Copied {src} -> {dst}"}

        @mcp.tool()
        def grep(
            path: str,
            pattern: str,
            max_matches: int = 25,
            recursive: bool = True,
            use_regex: bool = False,
            encoding: str = "utf-8",
        ) -> dict:
            """
            Search directory for pattern in file contents (grep-style).
            Returns matches as {path, line_number, line}. Truncates to max_matches.

            Args:
                path: Directory path relative to root to search in
                pattern: String to search for (substring or regex if use_regex)
                max_matches: Maximum number of matches to return (default: 100)
                recursive: Search subdirectories (default: True)
                use_regex: Treat pattern as regex (default: False)
                encoding: Text encoding for files (default: utf-8)

            Returns:
                Dict with success, matches (list of {path, line_number, line}), truncated (bool).
            """
            out = client.search_directory(
                path=path,
                pattern=pattern,
                max_matches=max_matches,
                recursive=recursive,
                use_regex=use_regex,
                encoding=encoding,
            )
            if out is None:
                return {
                    "success": False,
                    "error": "Directory not found, outside root, or invalid regex",
                    "matches": [],
                    "truncated": False,
                }
            matches, truncated = out
            return {"success": True, "matches": matches, "truncated": truncated}

        @mcp.tool()
        def read_pdf(path: str) -> dict:
            """
            Extract text from a PDF. Returns structured output the agent can parse:
            {pages: [{page, text, has_text_layer}], total_pages, extraction_method, warnings}.

            Args:
                path: PDF path relative to filesystem root

            Returns:
                Dict with success and either the structured PDF extraction
                (pages, total_pages, extraction_method, warnings) or error.
            """
            result = client.read_pdf(path)
            if result is None:
                return {
                    "success": False,
                    "error": "File not found, outside root, not a PDF, or extraction failed",
                    "pages": [],
                    "total_pages": 0,
                    "extraction_method": "text",
                    "warnings": [],
                }
            return {
                "success": True,
                **result,
            }


# Module instance for registry
module = FilesystemToolModule()
