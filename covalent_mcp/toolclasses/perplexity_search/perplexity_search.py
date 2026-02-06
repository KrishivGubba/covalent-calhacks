"""
Perplexity Search MCP Tools - Web search operations.

Exposes Perplexity Search API as MCP tools for LLM agents.
Registered as TOOLS (not resources) to avoid FastMCP query param issues.
"""
import json
import os
import sys
from pathlib import Path
from typing import Optional, List
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
        db_path = _PROJECT_ROOT / "context-engine" / "graph.db"
        auth_dao = AuthDAO(str(db_path))
        
        sessions = auth_dao.get_all_sessions()
        if not sessions:
            return None
        
        session = auth_dao.get_session(sessions[0]["user_id"])
        if session and session.get("access_token"):
            return session["access_token"]
        return None
    except Exception:
        return None


class PerplexitySearchToolModule(MCPToolModule):
    """
    Perplexity Search tool module for web search operations.
    
    Provides MCP tools for:
    - Basic web search
    - Regional web search  
    - Advanced web search with filters
    """
    
    def __init__(self):
        """Initialize Perplexity Search tool module."""
        self.client = None
    
    def _ensure_client(self) -> PerplexitySearchClient:
        """Ensure Perplexity Search client is initialized with auth token."""
        if self.client is None:
            auth_token = _get_auth_token()
            self.client = PerplexitySearchClient(auth_token=auth_token)
        return self.client
    
    def register(self, mcp: FastMCP) -> None:
        """Register Perplexity Search tools with MCP server."""
        # Capture self for lazy client initialization in closures
        tool_module = self
        
        @mcp.tool()
        def search_web(query: str, max_results: int = 10) -> str:
            """
            Search the web using Perplexity Search API.
            
            Use this tool to find current information, news, research, 
            or any real-time data from the internet.
            
            Args:
                query: Search query string (what to search for)
                max_results: Maximum number of results (1-20, default: 10)
            
            Returns:
                JSON string with search results including titles, URLs, and snippets
            """
            client = tool_module._ensure_client()
            results = client.search(query=query, max_results=max_results)
            return json.dumps(results, indent=2, default=str)
        
        @mcp.tool()
        def search_web_regional(query: str, country: str, max_results: int = 10) -> str:
            """
            Search the web with regional/country filtering.
            
            Use this for location-specific searches (e.g., news in a specific country).
            
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
        
        @mcp.tool()
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
    
    def register_resources(self, mcp: FastMCP) -> None:
        """No resources - using tools instead to avoid FastMCP query param issues."""
        pass


# Create module instance (required for registry pattern)
module = PerplexitySearchToolModule()
