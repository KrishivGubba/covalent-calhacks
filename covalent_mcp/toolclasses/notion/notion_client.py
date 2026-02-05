"""
Notion API Client - REST wrapper for Notion operations.

Provides methods for pages, blocks, databases/data sources, search, comments, and users.
Uses Notion API version 2022-06-28.
"""
import requests
from typing import Optional, Dict, Any, List


NOTION_API_VERSION = "2022-06-28"


class NotionClient:
    """
    Notion API client for page, block, database, search, and comment operations.
    
    Usage:
        client = NotionClient(access_token="ntn_...")
        results = client.search("My Page")
    """
    
    BASE_URL = "https://api.notion.com/v1"
    
    def __init__(self, access_token: str):
        """
        Initialize Notion client.
        
        Args:
            access_token: Notion OAuth access token or integration token
        """
        if not access_token:
            raise ValueError("access_token must be provided")
        self.access_token = access_token
    
    def _request(self, method: str, endpoint: str, **kwargs) -> Dict[str, Any]:
        """Make authenticated request to Notion API."""
        url = f"{self.BASE_URL}{endpoint}"
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Notion-Version": NOTION_API_VERSION,
            "Content-Type": "application/json",
        }
        headers.update(kwargs.pop("headers", {}))
        
        response = requests.request(method, url, headers=headers, **kwargs)
        response.raise_for_status()
        return response.json()
    
    # ========================================================================
    # Search
    # ========================================================================
    
    def search(
        self,
        query: str = "",
        filter_type: Optional[str] = None,
        sort_direction: Optional[str] = None,
        start_cursor: Optional[str] = None,
        page_size: int = 20,
    ) -> Dict[str, Any]:
        """
        Search pages and databases by title.
        
        Args:
            query: Text to search for in page/database titles
            filter_type: Filter by "page" or "database" (None for both)
            sort_direction: "ascending" or "descending" by last_edited_time
            start_cursor: Pagination cursor
            page_size: Number of results (max 100)
        
        Returns:
            Search results with pages/databases
        """
        data: Dict[str, Any] = {}
        if query:
            data["query"] = query
        if filter_type:
            data["filter"] = {"value": filter_type, "property": "object"}
        if sort_direction:
            data["sort"] = {"direction": sort_direction, "timestamp": "last_edited_time"}
        if start_cursor:
            data["start_cursor"] = start_cursor
        data["page_size"] = min(page_size, 100)
        
        return self._request("POST", "/search", json=data)
    
    # ========================================================================
    # Pages
    # ========================================================================
    
    def get_page(self, page_id: str) -> Dict[str, Any]:
        """
        Retrieve a page by ID.
        
        Args:
            page_id: Notion page ID (UUID)
        
        Returns:
            Page object with properties
        """
        return self._request("GET", f"/pages/{page_id}")
    
    def create_page(
        self,
        parent_type: str,
        parent_id: str,
        properties: Dict[str, Any],
        children: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """
        Create a new page.
        
        Args:
            parent_type: "page_id" or "database_id"
            parent_id: ID of the parent page or database
            properties: Page properties (title, etc.)
            children: Optional list of block objects for page content
        
        Returns:
            Created page object
        """
        data: Dict[str, Any] = {
            "parent": {parent_type: parent_id},
            "properties": properties,
        }
        if children:
            data["children"] = children
        
        return self._request("POST", "/pages", json=data)
    
    def update_page(
        self,
        page_id: str,
        properties: Optional[Dict[str, Any]] = None,
        archived: Optional[bool] = None,
        icon: Optional[str] = None,
        cover_url: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Update a page's properties.
        
        Args:
            page_id: Notion page ID
            properties: Property values to update
            archived: Set to True to archive (delete), False to restore
            icon: Emoji icon for the page
            cover_url: External URL for cover image
        
        Returns:
            Updated page object
        """
        data: Dict[str, Any] = {}
        if properties:
            data["properties"] = properties
        if archived is not None:
            data["archived"] = archived
        if icon:
            data["icon"] = {"emoji": icon}
        if cover_url:
            data["cover"] = {"type": "external", "external": {"url": cover_url}}
        
        return self._request("PATCH", f"/pages/{page_id}", json=data)
    
    def get_page_property(
        self,
        page_id: str,
        property_id: str,
        start_cursor: Optional[str] = None,
        page_size: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Retrieve a specific page property.
        
        Args:
            page_id: Notion page ID
            property_id: Property ID
            start_cursor: Pagination cursor for paginated properties
            page_size: Number of items per page
        
        Returns:
            Property item object
        """
        params: Dict[str, Any] = {}
        if start_cursor:
            params["start_cursor"] = start_cursor
        if page_size:
            params["page_size"] = page_size
        
        return self._request("GET", f"/pages/{page_id}/properties/{property_id}", params=params)
    
    # ========================================================================
    # Blocks
    # ========================================================================
    
    def get_block(self, block_id: str) -> Dict[str, Any]:
        """
        Retrieve a block by ID.
        
        Args:
            block_id: Notion block ID
        
        Returns:
            Block object
        """
        return self._request("GET", f"/blocks/{block_id}")
    
    def get_block_children(
        self,
        block_id: str,
        start_cursor: Optional[str] = None,
        page_size: int = 100,
    ) -> Dict[str, Any]:
        """
        Retrieve children of a block (page content).
        
        Args:
            block_id: Block or page ID
            start_cursor: Pagination cursor
            page_size: Number of results (max 100)
        
        Returns:
            List of child blocks
        """
        params: Dict[str, Any] = {"page_size": min(page_size, 100)}
        if start_cursor:
            params["start_cursor"] = start_cursor
        
        return self._request("GET", f"/blocks/{block_id}/children", params=params)
    
    def append_block_children(
        self,
        block_id: str,
        children: List[Dict[str, Any]],
        after: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Append content to a block (add blocks to a page).
        
        Args:
            block_id: Block or page ID to append to
            children: List of block objects to append
            after: ID of existing block to append after
        
        Returns:
            Response with appended blocks
        """
        data: Dict[str, Any] = {"children": children}
        if after:
            data["after"] = after
        
        return self._request("PATCH", f"/blocks/{block_id}/children", json=data)
    
    def update_block(
        self,
        block_id: str,
        block_data: Optional[Dict[str, Any]] = None,
        archived: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """
        Update a block.
        
        Args:
            block_id: Notion block ID
            block_data: Block type-specific data to update
            archived: Set to True to archive (delete)
        
        Returns:
            Updated block object
        """
        data: Dict[str, Any] = {}
        if block_data:
            data.update(block_data)
        if archived is not None:
            data["archived"] = archived
        
        return self._request("PATCH", f"/blocks/{block_id}", json=data)
    
    def delete_block(self, block_id: str) -> Dict[str, Any]:
        """
        Delete a block.
        
        Args:
            block_id: Notion block ID
        
        Returns:
            Deleted block object
        """
        return self._request("DELETE", f"/blocks/{block_id}")
    
    # ========================================================================
    # Databases / Data Sources
    # ========================================================================
    
    def get_database(self, database_id: str) -> Dict[str, Any]:
        """
        Retrieve a database by ID.
        
        Args:
            database_id: Notion database ID
        
        Returns:
            Database object with schema
        """
        return self._request("GET", f"/databases/{database_id}")
    
    def query_database(
        self,
        database_id: str,
        filter: Optional[Dict[str, Any]] = None,
        sorts: Optional[List[Dict[str, Any]]] = None,
        start_cursor: Optional[str] = None,
        page_size: int = 100,
    ) -> Dict[str, Any]:
        """
        Query a database with filters and sorts.
        
        Args:
            database_id: Notion database ID
            filter: Filter conditions
            sorts: Sort conditions (list of {property, direction})
            start_cursor: Pagination cursor
            page_size: Number of results (max 100)
        
        Returns:
            Query results with pages
        """
        data: Dict[str, Any] = {"page_size": min(page_size, 100)}
        if filter:
            data["filter"] = filter
        if sorts:
            data["sorts"] = sorts
        if start_cursor:
            data["start_cursor"] = start_cursor
        
        return self._request("POST", f"/databases/{database_id}/query", json=data)
    
    def create_database(
        self,
        parent_page_id: str,
        title: str,
        properties: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Create a new database (as a child of a page).
        
        Args:
            parent_page_id: Parent page ID
            title: Database title
            properties: Database property schema
        
        Returns:
            Created database object
        """
        data: Dict[str, Any] = {
            "parent": {"page_id": parent_page_id},
            "title": [{"type": "text", "text": {"content": title}}],
            "properties": properties,
        }
        
        return self._request("POST", "/databases", json=data)
    
    def update_database(
        self,
        database_id: str,
        title: Optional[str] = None,
        description: Optional[str] = None,
        properties: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Update a database's title, description, or properties.
        
        Args:
            database_id: Notion database ID
            title: New title
            description: New description
            properties: Property schema updates
        
        Returns:
            Updated database object
        """
        data: Dict[str, Any] = {}
        if title:
            data["title"] = [{"type": "text", "text": {"content": title}}]
        if description:
            data["description"] = [{"type": "text", "text": {"content": description}}]
        if properties:
            data["properties"] = properties
        
        return self._request("PATCH", f"/databases/{database_id}", json=data)
    
    # ========================================================================
    # Comments
    # ========================================================================
    
    def get_comments(
        self,
        block_id: str,
        start_cursor: Optional[str] = None,
        page_size: int = 100,
    ) -> Dict[str, Any]:
        """
        Retrieve comments on a page or block.
        
        Args:
            block_id: Page or block ID
            start_cursor: Pagination cursor
            page_size: Number of results (max 100)
        
        Returns:
            List of comment objects
        """
        params: Dict[str, Any] = {
            "block_id": block_id,
            "page_size": min(page_size, 100),
        }
        if start_cursor:
            params["start_cursor"] = start_cursor
        
        return self._request("GET", "/comments", params=params)
    
    def create_comment(
        self,
        page_id: str,
        content: str,
    ) -> Dict[str, Any]:
        """
        Create a comment on a page.
        
        Args:
            page_id: Page ID to comment on
            content: Comment text content
        
        Returns:
            Created comment object
        """
        data = {
            "parent": {"page_id": page_id},
            "rich_text": [{"text": {"content": content}}],
        }
        
        return self._request("POST", "/comments", json=data)
    
    # ========================================================================
    # Users
    # ========================================================================
    
    def get_me(self) -> Dict[str, Any]:
        """
        Get the bot user associated with the current token.
        
        Returns:
            Bot user object
        """
        return self._request("GET", "/users/me")
    
    def get_user(self, user_id: str) -> Dict[str, Any]:
        """
        Retrieve a user by ID.
        
        Args:
            user_id: Notion user ID
        
        Returns:
            User object
        """
        return self._request("GET", f"/users/{user_id}")
    
    def list_users(
        self,
        start_cursor: Optional[str] = None,
        page_size: int = 100,
    ) -> Dict[str, Any]:
        """
        List all users in the workspace.
        
        Args:
            start_cursor: Pagination cursor
            page_size: Number of results (max 100)
        
        Returns:
            List of user objects
        """
        params: Dict[str, Any] = {"page_size": min(page_size, 100)}
        if start_cursor:
            params["start_cursor"] = start_cursor
        
        return self._request("GET", "/users", params=params)
