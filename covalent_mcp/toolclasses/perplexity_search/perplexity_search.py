"""
Perplexity Search MCP Resources - Web search operations.

Exposes Perplexity Search API as MCP resources (read-only) for LLM agents.
"""
import json
import os
import sys
from pathlib import Path
from typing import Dict, Optional, List
from covalent_mcp.toolclasses.base import MCPToolModule
from covalent_mcp.toolclasses.perplexity_search.perplexity_search_client import PerplexitySearchClient
from fastmcp import FastMCP

# Add server path for AuthDAO
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(_PROJECT_ROOT / "server"))


def _get_auth_token() -> Optional[str]:
    """Get auth token from database for Perplexity API calls."""
    try:
        from auth_dao import AuthDAO
        db_path = os.environ.get('GRAPH_DB_PATH', str(_PROJECT_ROOT / "context-engine" / "graph.db"))
        print(f"🔑 [Perplexity] Looking for auth token in DB: {db_path}")
        print(f"   DB exists: {os.path.exists(db_path)}")
        print(f"   GRAPH_DB_PATH env: {os.environ.get('GRAPH_DB_PATH', '(not set)')}")
        
        auth_dao = AuthDAO(str(db_path))
        
        sessions = auth_dao.get_all_sessions()
        if not sessions:
            print("   ⚠️  No user sessions found in DB")
            return None
        
        print(f"   Found {len(sessions)} session(s), user: {sessions[0]['user_id'][:30]}...")
        session = auth_dao.get_session(sessions[0]["user_id"])
        if session and session.get("access_token"):
            token = session["access_token"]
            print(f"   ✅ Got access token: {token[:20]}...")
            return token
        
        print("   ⚠️  Session exists but no access_token")
        return None
    except Exception as e:
        print(f"   ❌ _get_auth_token FAILED: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return None


class PerplexitySearchToolModule(MCPToolModule):
    """
    Perplexity Search module for web search operations.
    
    All functions are registered as MCP **resources** (read-only).
    
    Provides MCP resources for:
    - Basic web search
    - Regional web search
    - Advanced web search with filters
    """
    
    def __init__(self):
        """Initialize Perplexity Search tool module."""
        self.client = None
    
    def _ensure_client(self) -> PerplexitySearchClient:
        """Ensure Perplexity Search client is initialized with a fresh auth token."""
        auth_token = _get_auth_token()
        if self.client is None:
            self.client = PerplexitySearchClient(auth_token=auth_token)
        else:
            self.client.auth_token = auth_token
        return self.client

    def register(self, mcp: FastMCP) -> None:
        """No tools - all search operations are resources (read-only)."""
        pass
    
    def register_resources(self, mcp: FastMCP) -> None:
        """Register Perplexity Search resources with MCP server."""
        tool_module = self
        
        @mcp.resource("perplexity://search/{query}")
        def search_web(query: str, max_results: int = 10) -> str:
            """
            Search the web using Perplexity Search API.
            
            Use this resource to find current information, news, research, 
            or any real-time data from the internet.
            
            URI: perplexity://search/{query}
            
            Args:
                query: Search query string (what to search for)
                max_results: Maximum number of results (1-20, default: 10)
            
            Returns:
                JSON string with search results including titles, URLs, and snippets
            """
            client = tool_module._ensure_client()
            results = client.search(query=query, max_results=max_results)
            return json.dumps(results, indent=2, default=str)
        
        @mcp.resource("perplexity://search/{query}/region/{country}")
        def search_web_regional(query: str, country: str, max_results: int = 10) -> str:
            """
            Search the web with regional/country filtering.
            
            Use this for location-specific searches (e.g., news in a specific country).
            
            URI: perplexity://search/{query}/region/{country}
            
            Args:
                query: Search query string
                country: ISO 3166-1 alpha-2 country code (e.g., "US", "GB", "DE", "JP", "IN")
                max_results: Maximum number of results (1-20, default: 10)
            
            Returns:
                JSON string with search results filtered by country
            """
            client = tool_module._ensure_client()
            results = client.search(query=query, country=country, max_results=max_results)
            return json.dumps(results, indent=2, default=str)
        
        @mcp.resource("perplexity://search/advanced/{query}{?country,domains,recency,mode}")
        def search_web_advanced(
            query: str,
            max_results: int = 10,
            country: Optional[str] = None,
            domains: Optional[str] = None,
            recency: Optional[str] = None,
            mode: Optional[str] = None,
        ) -> str:
            """
            Advanced web search with multiple filters.
            
            Use this for specialized searches with domain filtering, recency, or academic mode.
            
            URI: perplexity://search/advanced/{query}
            
            Args:
                query: Search query string
                max_results: Maximum number of results (1-20, default: 10)
                country: ISO 3166-1 alpha-2 country code (e.g., "US", "GB")
                domains: Comma-separated domains to filter (e.g., "nytimes.com,bbc.com" or "-pinterest.com" to exclude)
                recency: Filter by recency - "hour", "day", "week", "month", "year"
                mode: Search mode - "web" (default), "academic" (scholarly), or "sec" (financial filings)
            
            Returns:
                JSON string with filtered search results
            """
            client = tool_module._ensure_client()
            search_params = {
                "query": query,
                "max_results": max_results,
            }
            
            if country:
                search_params["country"] = country
            if domains:
                domain_list = [d.strip() for d in domains.split(",")][:20]
                search_params["search_domain_filter"] = domain_list
            if mode:
                search_params["search_mode"] = mode
            if recency:
                search_params["search_recency_filter"] = recency
            
            results = client.search(**search_params)
            return json.dumps(results, indent=2, default=str)


# Create module instance (required for registry pattern)
module = PerplexitySearchToolModule()
