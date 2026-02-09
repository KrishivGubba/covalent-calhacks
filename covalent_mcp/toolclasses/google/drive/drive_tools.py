"""
Google Drive MCP Tools - File and folder operations.

Exposes Google Drive operations as MCP tools and resources for LLM agents.
Token is managed by the server via OAuth flow - MCP reads token from database.
"""
import json
from typing import Dict, Optional
from covalent_mcp.toolclasses.base import (
    MCPToolModule,
    ToolDisplaySchema,
    DisplayField,
)
from covalent_mcp.toolclasses.google.drive.drive_client import DriveService
from fastmcp import FastMCP


class DriveToolModule(MCPToolModule):
    """
    Google Drive tool module for file and folder operations.
    
    Provides MCP tools for:
    - Creating/updating/deleting files and folders
    - Renaming and moving files
    
    Provides MCP resources for:
    - Listing folders
    - Getting file information
    - Getting file content
    """
    
    def __init__(self):
        """Initialize Drive tool module."""
        self._client = None
    
    def _ensure_client(self) -> DriveService:
        """Ensure Drive client is initialized with credentials from database."""
        if self._client is None:
            # DriveService reads token from database via get_credentials_from_db()
            self._client = DriveService()
        return self._client

    # -----------------------------------------------------------------
    # Resolve helpers
    # -----------------------------------------------------------------

    async def _resolve_file_details(self, params: dict) -> dict:
        """Fetch file metadata from Drive so the approval UI can show the file name."""
        file_id = params.get("file_id", "")
        if not file_id:
            return {}
        try:
            client = self._ensure_client()
            meta = client.get_file(file_id)
            if not meta:
                return {"file_name": "(file not found)"}
            return {
                "file_name": meta.get("name", "(unknown)"),
                "file_type": meta.get("mimeType", ""),
            }
        except Exception as e:
            print(f"Warning: failed to resolve Drive file details for {file_id}: {e}")
            return {"file_name": "(could not load file info)"}

    # -----------------------------------------------------------------
    # Display schemas
    # -----------------------------------------------------------------

    def get_display_schemas(self) -> Dict[str, ToolDisplaySchema]:
        """Return display schemas for Drive tools."""
        return {
            "create_text_file": ToolDisplaySchema(
                tool_name="create_text_file",
                display_name="Create File in Drive",
                description="Create a new text file in Google Drive.",
                fields=[
                    DisplayField(key="name", label="File Name", required=True, widget="text_input", placeholder="notes.txt"),
                    DisplayField(key="content", label="Content", required=True, widget="textarea"),
                ],
            ),
            "update_text_file": ToolDisplaySchema(
                tool_name="update_text_file",
                display_name="Update File in Drive",
                description="Update an existing text file in Google Drive.",
                fields=[
                    DisplayField(key="file_name", label="File", source="resolved", editable=False, widget="display_text"),
                    DisplayField(key="name", label="New Name", widget="text_input", placeholder="Leave blank to keep current name"),
                    DisplayField(key="content", label="New Content", required=True, widget="textarea"),
                ],
                resolve=self._resolve_file_details,
            ),
            "create_folder": ToolDisplaySchema(
                tool_name="create_folder",
                display_name="Create Folder in Drive",
                description="Create a new folder in Google Drive.",
                fields=[
                    DisplayField(key="name", label="Folder Name", required=True, widget="text_input"),
                ],
            ),
            "delete_file": ToolDisplaySchema(
                tool_name="delete_file",
                display_name="Delete File from Drive",
                description="Move a file or folder to trash in Google Drive.",
                fields=[
                    DisplayField(key="file_name", label="File", source="resolved", editable=False, widget="display_text"),
                    DisplayField(key="file_type", label="Type", source="resolved", editable=False, widget="display_text"),
                ],
                resolve=self._resolve_file_details,
            ),
            "rename_file": ToolDisplaySchema(
                tool_name="rename_file",
                display_name="Rename File in Drive",
                description="Rename a file or folder in Google Drive.",
                fields=[
                    DisplayField(key="file_name", label="Current Name", source="resolved", editable=False, widget="display_text"),
                    DisplayField(key="new_name", label="New Name", required=True, widget="text_input"),
                ],
                resolve=self._resolve_file_details,
            ),
            "move_file": ToolDisplaySchema(
                tool_name="move_file",
                display_name="Move File in Drive",
                description="Move a file or folder to a different location.",
                fields=[
                    DisplayField(key="file_name", label="File", source="resolved", editable=False, widget="display_text"),
                    DisplayField(key="destination_folder_id", label="Destination Folder ID", widget="text_input"),
                ],
                resolve=self._resolve_file_details,
            ),
        }
    
    def register(self, mcp: FastMCP) -> None:
        """Register Drive tools (write operations) with MCP server."""
        tool_module = self
        
        @mcp.tool()
        def create_text_file(
            name: str,
            content: str,
            parent_folder_id: Optional[str] = None
        ) -> dict:
            """
            Create a new text file in Google Drive.
            
            Args:
                name: File name (must end with .txt, .md, or .json)
                content: File content
                parent_folder_id: Parent folder ID (defaults to root)
            
            Returns:
                Created file information including ID and web view link
            """
            client = tool_module._ensure_client()
            file = client.create_text_file(
                name=name,
                content=content,
                parent_folder_id=parent_folder_id
            )
            
            if not file:
                return {"success": False, "error": "Failed to create file"}
            
            return {
                "success": True,
                "id": file.get("id"),
                "name": file.get("name"),
                "webViewLink": file.get("webViewLink"),
                "message": f"Created file: {file.get('name')}"
            }
        
        @mcp.tool()
        def update_text_file(
            file_id: str,
            content: str,
            name: Optional[str] = None
        ) -> dict:
            """
            Update an existing text file in Google Drive.
            
            Args:
                file_id: File ID to update
                content: New file content
                name: Optional new file name
            
            Returns:
                Updated file information
            """
            client = tool_module._ensure_client()
            file = client.update_text_file(
                file_id=file_id,
                content=content,
                name=name
            )
            
            if not file:
                return {"success": False, "error": "Failed to update file"}
            
            return {
                "success": True,
                "id": file.get("id"),
                "name": file.get("name"),
                "webViewLink": file.get("webViewLink"),
                "message": f"Updated file: {file.get('name')}"
            }
        
        @mcp.tool()
        def create_folder(
            name: str,
            parent_folder_id: Optional[str] = None
        ) -> dict:
            """
            Create a new folder in Google Drive.
            
            Args:
                name: Folder name
                parent_folder_id: Parent folder ID (defaults to root)
            
            Returns:
                Created folder information including ID and web view link
            """
            client = tool_module._ensure_client()
            folder = client.create_folder(
                name=name,
                parent_folder_id=parent_folder_id
            )
            
            if not folder:
                return {"success": False, "error": "Failed to create folder"}
            
            return {
                "success": True,
                "id": folder.get("id"),
                "name": folder.get("name"),
                "webViewLink": folder.get("webViewLink"),
                "message": f"Created folder: {folder.get('name')}"
            }
        
        @mcp.tool()
        def delete_file(file_id: str) -> dict:
            """
            Move a file or folder to trash in Google Drive.
            
            Args:
                file_id: File or folder ID to delete
            
            Returns:
                Success status
            """
            client = tool_module._ensure_client()
            success = client.delete_file(file_id)
            
            return {
                "success": success,
                "message": "File moved to trash" if success else "Failed to delete file"
            }
        
        @mcp.tool()
        def rename_file(file_id: str, new_name: str) -> dict:
            """
            Rename a file or folder in Google Drive.
            
            Args:
                file_id: File or folder ID to rename
                new_name: New name
            
            Returns:
                Updated file information
            """
            client = tool_module._ensure_client()
            file = client.rename_file(file_id, new_name)
            
            if not file:
                return {"success": False, "error": "Failed to rename file"}
            
            return {
                "success": True,
                "id": file.get("id"),
                "name": file.get("name"),
                "message": f"Renamed to: {file.get('name')}"
            }
        
        @mcp.tool()
        def move_file(
            file_id: str,
            destination_folder_id: Optional[str] = None
        ) -> dict:
            """
            Move a file or folder to a different folder in Google Drive.
            
            Args:
                file_id: File or folder ID to move
                destination_folder_id: Destination folder ID (defaults to root)
            
            Returns:
                Updated file information
            """
            client = tool_module._ensure_client()
            file = client.move_file(file_id, destination_folder_id)
            
            if not file:
                return {"success": False, "error": "Failed to move file"}
            
            return {
                "success": True,
                "id": file.get("id"),
                "name": file.get("name"),
                "message": f"Moved file: {file.get('name')}"
            }
    
    def register_resources(self, mcp: FastMCP) -> None:
        """Register Drive resources (read operations) with MCP server."""
        tool_module = self
        
        @mcp.resource("gdrive://search/{query}{?max_results,page_token}")
        def search_files_resource(
            query: str,
            max_results: int = 50,
            page_token: Optional[str] = None
        ) -> str:
            """
            Search for files in Google Drive.
            
            URI: gdrive://search/{query}{?max_results,page_token}
            Path param: query - Search query (e.g., "name contains 'test'")
            Optional query params: max_results (1-100, default 50), page_token (pagination)
            """
            client = tool_module._ensure_client()
            result = client.search_files(
                query=query,
                max_results=max_results,
                page_token=page_token
            )
            
            return json.dumps({
                "count": len(result.get("files", [])),
                "files": result.get("files", []),
                "nextPageToken": result.get("nextPageToken")
            }, indent=2)
        
        @mcp.resource("gdrive://folder/{folder_id}")
        def list_folder_resource(
            folder_id: str,
            max_results: int = 50,
            page_token: Optional[str] = None
        ) -> str:
            """
            List contents of a folder.
            
            URI: gdrive://folder/{folder_id}
            Use 'root' as folder_id for root folder.
            Optional query params:
            - max_results: Maximum results (1-100, default: 50)
            - page_token: Token for pagination
            """
            client = tool_module._ensure_client()
            result = client.list_folder(
                folder_id=folder_id if folder_id != 'root' else None,
                max_results=max_results,
                page_token=page_token
            )
            
            return json.dumps({
                "count": len(result.get("files", [])),
                "folder_id": folder_id,
                "files": result.get("files", []),
                "nextPageToken": result.get("nextPageToken")
            }, indent=2)
        
        @mcp.resource("gdrive://file/{file_id}")
        def get_file_resource(file_id: str) -> str:
            """
            Get file metadata.
            
            URI: gdrive://file/{file_id}
            """
            client = tool_module._ensure_client()
            file = client.get_file(file_id)
            if not file:
                return json.dumps({"error": "File not found"}, indent=2)
            return json.dumps(file, indent=2)
        
        @mcp.resource("gdrive://file/{file_id}/content")
        def get_file_content_resource(file_id: str) -> str:
            """
            Get file content as text.
            
            URI: gdrive://file/{file_id}/content
            For Google Docs/Sheets/Slides, exports as text/markdown/CSV.
            """
            client = tool_module._ensure_client()
            content = client.get_file_content(file_id)
            if content is None:
                return json.dumps({"error": "Failed to get file content"}, indent=2)
            return json.dumps({
                "file_id": file_id,
                "content": content
            }, indent=2)


# Create module instance (required for registry pattern)
module = DriveToolModule()
