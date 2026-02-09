"""
Notion MCP Tools - Page, Block, Database, Search, and Comment operations.

Exposes Notion operations as MCP tools and resources for LLM agents.
"""
import json
import os
import sys
from typing import Optional, List, Dict, Any
from covalent_mcp.toolclasses.base import (
    MCPToolModule,
    ToolDisplaySchema,
    DisplayField,
)
from covalent_mcp.toolclasses.notion.notion_client import NotionClient
from fastmcp import FastMCP

# Path to integration DB for reading access token
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
DB_PATH = os.path.join(PROJECT_ROOT, 'context-engine', 'graph.db')


def _get_notion_token() -> Optional[str]:
    """
    Get Notion access token from integration_tokens DB.
    Falls back to NOTION_API_KEY env var if DB not available.
    """
    # Try reading from integration_tokens table
    try:
        sys.path.insert(0, PROJECT_ROOT)
        from server.integration_dao import IntegrationDAO
        dao = IntegrationDAO(DB_PATH)
        token_data = dao.get_token("notion")
        if token_data and token_data.get("access_token"):
            return token_data["access_token"]
    except Exception:
        pass
    
    # Fallback to env var
    return os.getenv("NOTION_API_KEY")


class NotionToolModule(MCPToolModule):
    """
    Notion tool module for page, block, database, search, and comment operations.
    
    Provides MCP tools for:
    - Searching pages and databases
    - Creating/updating pages
    - Reading/appending/deleting blocks (page content)
    - Querying/creating databases
    - Creating comments
    
    Provides MCP resources for:
    - Getting pages, blocks, databases
    - Listing users
    """
    
    def __init__(self):
        """Initialize Notion tool module."""
        self.client = None
    
    def _ensure_client(self) -> NotionClient:
        """Ensure Notion client is initialized with token from DB."""
        if self.client is None:
            token = _get_notion_token()
            if not token:
                raise RuntimeError(
                    "Notion not connected. Please connect Notion from the Integrations page."
                )
            self.client = NotionClient(access_token=token)
        return self.client
    
    # -----------------------------------------------------------------
    # Resolve helpers
    # -----------------------------------------------------------------

    async def _resolve_page_title(self, params: dict) -> dict:
        """Fetch page title from Notion so the UI shows a human-readable name."""
        page_id = params.get("page_id", "")
        if not page_id:
            return {}
        try:
            client = self._ensure_client()
            page = client.get_page(page_id)
            return {"page_title": _extract_title(page)}
        except Exception as e:
            print(f"Warning: failed to resolve Notion page title for {page_id}: {e}")
            return {"page_title": "(could not load page)"}

    async def _resolve_database_title(self, params: dict) -> dict:
        """Fetch database title from Notion."""
        db_id = params.get("database_id", "")
        if not db_id:
            return {}
        try:
            client = self._ensure_client()
            db = client.get_database(db_id)
            return {"database_title": _extract_title(db)}
        except Exception as e:
            print(f"Warning: failed to resolve Notion database title for {db_id}: {e}")
            return {"database_title": "(could not load database)"}

    async def _resolve_parent_title(self, params: dict) -> dict:
        """Resolve the parent page title for create operations."""
        parent_id = params.get("parent_id") or params.get("parent_page_id", "")
        if not parent_id:
            return {}
        try:
            client = self._ensure_client()
            page = client.get_page(parent_id)
            return {"parent_title": _extract_title(page)}
        except Exception:
            return {"parent_title": "(could not load parent)"}

    # -----------------------------------------------------------------
    # Display schemas
    # -----------------------------------------------------------------

    def get_display_schemas(self) -> Dict[str, ToolDisplaySchema]:
        """Return display schemas for Notion tools."""
        return {
            "notion_search": ToolDisplaySchema(
                tool_name="notion_search",
                display_name="Search Notion",
                description="Search pages and databases in Notion.",
                fields=[
                    DisplayField(key="query", label="Search Query", widget="text_input", placeholder="Search by title..."),
                    DisplayField(
                        key="filter_type", label="Filter", widget="select",
                        options=[
                            {"value": "", "label": "All"},
                            {"value": "page", "label": "Pages only"},
                            {"value": "database", "label": "Databases only"},
                        ],
                    ),
                ],
            ),
            "notion_create_page": ToolDisplaySchema(
                tool_name="notion_create_page",
                display_name="Create Notion Page",
                description="Create a new page in Notion.",
                fields=[
                    DisplayField(key="parent_title", label="Parent", source="resolved", editable=False, widget="display_text"),
                    DisplayField(
                        key="parent_type", label="Parent Type", required=True, widget="select",
                        options=[
                            {"value": "page_id", "label": "Sub-page"},
                            {"value": "database_id", "label": "Database entry"},
                        ],
                    ),
                    DisplayField(key="title", label="Page Title", required=True, widget="text_input"),
                    DisplayField(key="content", label="Content", widget="textarea", placeholder="Page body text..."),
                    DisplayField(key="icon", label="Icon", widget="text_input", placeholder="Emoji, e.g. \U0001f4dd"),
                ],
                resolve=self._resolve_parent_title,
            ),
            "notion_update_page": ToolDisplaySchema(
                tool_name="notion_update_page",
                display_name="Update Notion Page",
                description="Update properties or archive a Notion page.",
                fields=[
                    DisplayField(key="page_title", label="Page", source="resolved", editable=False, widget="display_text"),
                    DisplayField(key="properties", label="Properties (JSON)", widget="textarea", placeholder='{"Status": {"select": {"name": "Done"}}}'),
                    DisplayField(key="archived", label="Archive", widget="toggle"),
                    DisplayField(key="icon", label="Icon", widget="text_input", placeholder="Emoji"),
                ],
                resolve=self._resolve_page_title,
            ),
            "notion_append_blocks": ToolDisplaySchema(
                tool_name="notion_append_blocks",
                display_name="Append to Notion Page",
                description="Append content blocks to a Notion page.",
                fields=[
                    DisplayField(key="page_title", label="Page", source="resolved", editable=False, widget="display_text"),
                    DisplayField(key="content", label="Content", required=True, widget="textarea"),
                    DisplayField(
                        key="block_type", label="Block Type", widget="select",
                        options=[
                            {"value": "paragraph", "label": "Paragraph"},
                            {"value": "bulleted_list_item", "label": "Bulleted List"},
                        ],
                    ),
                ],
                resolve=self._resolve_page_title,
            ),
            "notion_delete_block": ToolDisplaySchema(
                tool_name="notion_delete_block",
                display_name="Delete Notion Block",
                description="Delete a block from a Notion page.",
                fields=[
                    DisplayField(key="block_id", label="Block ID", required=True, editable=False, widget="display_text"),
                ],
            ),
            "notion_query_database": ToolDisplaySchema(
                tool_name="notion_query_database",
                display_name="Query Notion Database",
                description="Query a Notion database with filters.",
                fields=[
                    DisplayField(key="database_title", label="Database", source="resolved", editable=False, widget="display_text"),
                    DisplayField(key="filter_json", label="Filter (JSON)", widget="textarea", placeholder="Optional filter conditions..."),
                    DisplayField(key="sorts_json", label="Sort (JSON)", widget="textarea", placeholder='[{"property":"Name","direction":"ascending"}]'),
                ],
                resolve=self._resolve_database_title,
            ),
            "notion_create_database": ToolDisplaySchema(
                tool_name="notion_create_database",
                display_name="Create Notion Database",
                description="Create a new database as a child of a page.",
                fields=[
                    DisplayField(key="parent_title", label="Parent Page", source="resolved", editable=False, widget="display_text"),
                    DisplayField(key="title", label="Database Title", required=True, widget="text_input"),
                    DisplayField(key="properties_json", label="Properties Schema (JSON)", required=True, widget="textarea",
                                 placeholder='{"Name": {"title": {}}, "Status": {"select": {}}}'),
                ],
                resolve=self._resolve_parent_title,
            ),
            "notion_create_comment": ToolDisplaySchema(
                tool_name="notion_create_comment",
                display_name="Comment on Notion Page",
                description="Add a comment to a Notion page.",
                fields=[
                    DisplayField(key="page_title", label="Page", source="resolved", editable=False, widget="display_text"),
                    DisplayField(key="content", label="Comment", required=True, widget="textarea", placeholder="Write your comment..."),
                ],
                resolve=self._resolve_page_title,
            ),
        }

    def register(self, mcp: FastMCP) -> None:
        """Register Notion tools (write operations) with MCP server."""
        module = self  # Capture reference for closures
        
        @mcp.tool()
        def notion_search(
            query: str = "",
            filter_type: Optional[str] = None,
            page_size: int = 20,
        ) -> dict:
            """
            Search Notion pages and databases by title.
            
            Args:
                query: Text to search for in page/database titles. Empty string returns recent items.
                filter_type: Filter by "page" or "database" (omit for both)
                page_size: Number of results to return (max 100)
            
            Returns:
                Search results with matching pages and databases
            """
            client = module._ensure_client()
            results = client.search(query=query, filter_type=filter_type, page_size=page_size)
            items = results.get("results", [])
            return {
                "success": True,
                "count": len(items),
                "has_more": results.get("has_more", False),
                "results": [
                    {
                        "id": item.get("id"),
                        "type": item.get("object"),
                        "title": _extract_title(item),
                        "url": item.get("url"),
                        "last_edited": item.get("last_edited_time"),
                    }
                    for item in items
                ],
            }
        
        @mcp.tool()
        def notion_create_page(
            parent_type: str,
            parent_id: str,
            title: str,
            content: Optional[str] = None,
            icon: Optional[str] = None,
        ) -> dict:
            """
            Create a new Notion page.
            
            Args:
                parent_type: "page_id" to create as subpage, or "database_id" to add to a database
                parent_id: ID of the parent page or database
                title: Page title
                content: Optional text content for the page body (plain text, added as paragraph blocks)
                icon: Optional emoji icon for the page (e.g. "📝")
            
            Returns:
                Created page info with ID and URL
            """
            client = module._ensure_client()
            
            # Build properties based on parent type
            if parent_type == "database_id":
                properties = {"title": {"title": [{"text": {"content": title}}]}}
            else:
                properties = {"title": {"title": [{"text": {"content": title}}]}}
            
            # Build children blocks if content provided
            children = None
            if content:
                # Split content into paragraphs
                paragraphs = content.split("\n\n") if "\n\n" in content else [content]
                children = [
                    {
                        "type": "paragraph",
                        "paragraph": {
                            "rich_text": [{"type": "text", "text": {"content": p}}]
                        }
                    }
                    for p in paragraphs
                    if p.strip()
                ]
            
            page = client.create_page(
                parent_type=parent_type,
                parent_id=parent_id,
                properties=properties,
                children=children,
            )
            
            # Set icon if provided
            if icon and page.get("id"):
                client.update_page(page["id"], icon=icon)
            
            return {
                "success": True,
                "id": page.get("id"),
                "url": page.get("url"),
                "title": title,
            }
        
        @mcp.tool()
        def notion_update_page(
            page_id: str,
            properties: Optional[str] = None,
            archived: Optional[bool] = None,
            icon: Optional[str] = None,
        ) -> dict:
            """
            Update a Notion page's properties or archive it.
            
            Args:
                page_id: Notion page ID
                properties: JSON string of property values to update
                archived: Set to true to archive (delete), false to restore
                icon: Emoji icon to set (e.g. "📝")
            
            Returns:
                Updated page info
            """
            client = module._ensure_client()
            
            props = None
            if properties:
                props = json.loads(properties) if isinstance(properties, str) else properties
            
            page = client.update_page(
                page_id=page_id,
                properties=props,
                archived=archived,
                icon=icon,
            )
            return {
                "success": True,
                "id": page.get("id"),
                "url": page.get("url"),
                "archived": page.get("archived"),
            }
        
        @mcp.tool()
        def notion_append_blocks(
            page_id: str,
            content: str,
            block_type: str = "paragraph",
        ) -> dict:
            """
            Append content blocks to a Notion page.
            
            Args:
                page_id: Page or block ID to append to
                content: Text content to append. Separate multiple blocks with double newlines.
                block_type: Block type - "paragraph" or "bulleted_list_item"
            
            Returns:
                Info about appended blocks
            """
            client = module._ensure_client()
            
            # Split content into blocks
            parts = content.split("\n\n") if "\n\n" in content else [content]
            children = [
                {
                    "type": block_type,
                    block_type: {
                        "rich_text": [{"type": "text", "text": {"content": p}}]
                    }
                }
                for p in parts
                if p.strip()
            ]
            
            result = client.append_block_children(block_id=page_id, children=children)
            return {
                "success": True,
                "blocks_added": len(children),
            }
        
        @mcp.tool()
        def notion_delete_block(block_id: str) -> dict:
            """
            Delete a Notion block.
            
            Args:
                block_id: Block ID to delete
            
            Returns:
                Confirmation of deletion
            """
            client = module._ensure_client()
            client.delete_block(block_id)
            return {"success": True, "deleted": block_id}
        
        @mcp.tool()
        def notion_query_database(
            database_id: str,
            filter_json: Optional[str] = None,
            sorts_json: Optional[str] = None,
            page_size: int = 50,
        ) -> dict:
            """
            Query a Notion database with optional filters and sorts.
            
            Args:
                database_id: Database ID to query
                filter_json: Optional JSON string of filter conditions (Notion filter format)
                sorts_json: Optional JSON string of sort conditions (e.g. [{"property":"Name","direction":"ascending"}])
                page_size: Number of results (max 100)
            
            Returns:
                Query results with matching pages/rows
            """
            client = module._ensure_client()
            
            filter_obj = json.loads(filter_json) if filter_json else None
            sorts_obj = json.loads(sorts_json) if sorts_json else None
            
            results = client.query_database(
                database_id=database_id,
                filter=filter_obj,
                sorts=sorts_obj,
                page_size=page_size,
            )
            items = results.get("results", [])
            return {
                "success": True,
                "count": len(items),
                "has_more": results.get("has_more", False),
                "results": [
                    {
                        "id": item.get("id"),
                        "url": item.get("url"),
                        "title": _extract_title(item),
                        "last_edited": item.get("last_edited_time"),
                    }
                    for item in items
                ],
            }
        
        @mcp.tool()
        def notion_create_database(
            parent_page_id: str,
            title: str,
            properties_json: str,
        ) -> dict:
            """
            Create a new Notion database as a child of a page.
            
            Args:
                parent_page_id: Parent page ID
                title: Database title
                properties_json: JSON string of property schema (e.g. {"Name": {"title": {}}, "Status": {"select": {"options": [{"name": "Todo"}, {"name": "Done"}]}}})
            
            Returns:
                Created database info with ID and URL
            """
            client = module._ensure_client()
            
            properties = json.loads(properties_json) if isinstance(properties_json, str) else properties_json
            
            db = client.create_database(
                parent_page_id=parent_page_id,
                title=title,
                properties=properties,
            )
            return {
                "success": True,
                "id": db.get("id"),
                "url": db.get("url"),
                "title": title,
            }
        
        @mcp.tool()
        def notion_create_comment(
            page_id: str,
            content: str,
        ) -> dict:
            """
            Create a comment on a Notion page.
            
            Args:
                page_id: Page ID to comment on
                content: Comment text
            
            Returns:
                Created comment info
            """
            client = module._ensure_client()
            comment = client.create_comment(page_id=page_id, content=content)
            return {
                "success": True,
                "id": comment.get("id"),
                "created_time": comment.get("created_time"),
            }
    
    def register_resources(self, mcp: FastMCP) -> None:
        """Register Notion resources (read-only operations) with MCP server."""
        module = self
        
        @mcp.resource("notion://page/{page_id}")
        def get_page_resource(page_id: str) -> str:
            """
            Get a Notion page by ID.
            
            URI: notion://page/{page_id}
            """
            client = module._ensure_client()
            page = client.get_page(page_id)
            return json.dumps({
                "id": page.get("id"),
                "url": page.get("url"),
                "title": _extract_title(page),
                "created_time": page.get("created_time"),
                "last_edited_time": page.get("last_edited_time"),
                "archived": page.get("archived"),
                "properties": page.get("properties"),
            }, indent=2)
        
        @mcp.resource("notion://page/{page_id}/content")
        def get_page_content_resource(page_id: str) -> str:
            """
            Get the content (child blocks) of a Notion page.
            
            URI: notion://page/{page_id}/content
            """
            client = module._ensure_client()
            result = client.get_block_children(page_id)
            blocks = result.get("results", [])
            return json.dumps({
                "page_id": page_id,
                "block_count": len(blocks),
                "has_more": result.get("has_more", False),
                "blocks": [
                    {
                        "id": b.get("id"),
                        "type": b.get("type"),
                        "content": _extract_block_text(b),
                    }
                    for b in blocks
                ],
            }, indent=2)
        
        @mcp.resource("notion://database/{database_id}")
        def get_database_resource(database_id: str) -> str:
            """
            Get a Notion database schema/metadata.
            
            URI: notion://database/{database_id}
            """
            client = module._ensure_client()
            db = client.get_database(database_id)
            return json.dumps({
                "id": db.get("id"),
                "url": db.get("url"),
                "title": _extract_title(db),
                "created_time": db.get("created_time"),
                "last_edited_time": db.get("last_edited_time"),
                "properties": {
                    k: {"type": v.get("type"), "id": v.get("id")}
                    for k, v in db.get("properties", {}).items()
                },
            }, indent=2)
        
        @mcp.resource("notion://comments/{page_id}")
        def get_comments_resource(page_id: str) -> str:
            """
            Get comments on a Notion page.
            
            URI: notion://comments/{page_id}
            """
            client = module._ensure_client()
            result = client.get_comments(page_id)
            comments = result.get("results", [])
            return json.dumps({
                "page_id": page_id,
                "count": len(comments),
                "comments": [
                    {
                        "id": c.get("id"),
                        "created_time": c.get("created_time"),
                        "text": _extract_rich_text(c.get("rich_text", [])),
                    }
                    for c in comments
                ],
            }, indent=2)
        
        @mcp.resource("notion://me")
        def get_me_resource() -> str:
            """
            Get the current bot user info.
            
            URI: notion://me
            """
            client = module._ensure_client()
            me = client.get_me()
            return json.dumps({
                "id": me.get("id"),
                "name": me.get("name"),
                "type": me.get("type"),
                "avatar_url": me.get("avatar_url"),
            }, indent=2)


# ============================================================================
# Helper functions for extracting text from Notion objects
# ============================================================================

def _extract_title(obj: Dict[str, Any]) -> str:
    """Extract title text from a Notion page or database object."""
    # Try page title property
    properties = obj.get("properties", {})
    for prop in properties.values():
        if prop.get("type") == "title":
            title_items = prop.get("title", [])
            return "".join(t.get("plain_text", "") for t in title_items)
    
    # Try database title array
    title_array = obj.get("title", [])
    if isinstance(title_array, list) and title_array:
        return "".join(t.get("plain_text", "") for t in title_array)
    
    return "Untitled"


def _extract_rich_text(rich_text: List[Dict[str, Any]]) -> str:
    """Extract plain text from rich_text array."""
    return "".join(t.get("plain_text", "") for t in rich_text)


def _extract_block_text(block: Dict[str, Any]) -> str:
    """Extract text content from a block object."""
    block_type = block.get("type", "")
    block_data = block.get(block_type, {})
    
    if "rich_text" in block_data:
        return _extract_rich_text(block_data["rich_text"])
    elif "text" in block_data:
        return _extract_rich_text(block_data["text"])
    
    return ""


# Create module instance (required for registry pattern)
module = NotionToolModule()
