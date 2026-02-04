"""
Perplexity Search MCP Resources - Web search operations.

Exposes Perplexity Search API as MCP resources for LLM agents.
All operations are read-only (resources).
"""
import json
from typing import Optional, List
from covalent_mcp.toolclasses.base import MCPToolModule
from covalent_mcp.toolclasses.perplexity_search.perplexity_search_client import PerplexitySearchClient
from fastmcp import FastMCP


class PerplexitySearchToolModule(MCPToolModule):
    """
    Perplexity Search tool module for web search operations.
    
    Provides MCP resources for:
    - Basic web search
    - Regional web search
    - Multi-query web search
    - Domain-filtered search
    - Language-filtered search
    """
    
    def __init__(self):
        """Initialize Perplexity Search tool module."""
        self.client = None
    
    def _ensure_client(self) -> PerplexitySearchClient:
        """Ensure Perplexity Search client is initialized."""
        if self.client is None:
            self.client = PerplexitySearchClient()
        return self.client
    
    def register(self, mcp: FastMCP) -> None:
        """
        Register Perplexity Search tools with MCP server.
        
        Note: Perplexity Search is read-only, so we primarily use resources.
        This method is required by MCPToolModule but we don't register tools here.
        """
        pass  # No tools, only resources
    
    def register_resources(self, mcp: FastMCP) -> None:
        """Register Perplexity Search resources (read-only operations) with MCP server."""
        client = self._ensure_client()
        
        @mcp.resource("perplexity://search{?query,max_results}")
        def basic_search_resource(query: str, max_results: int = 10) -> str:
            """
            Perform a basic web search using Perplexity Search API.
            
            URI: perplexity://search{?query,max_results}
            
            Args:
                query: Search query string
                max_results: Maximum number of results (1-20, default: 10)
            
            Returns:
                JSON string with search results
            """
            results = client.search(query=query, max_results=max_results)
            return json.dumps(results, indent=2, default=str)
        
        @mcp.resource("perplexity://search/regional{?query,country,max_results}")
        def regional_search_resource(query: str, country: str, max_results: int = 10) -> str:
            """
            Perform a regional web search filtered by country.
            
            URI: perplexity://search/regional{?query,country,max_results}
            
            Args:
                query: Search query string
                country: ISO 3166-1 alpha-2 country code (e.g., "US", "GB", "DE", "JP")
                max_results: Maximum number of results (1-20, default: 10)
            
            Returns:
                JSON string with search results filtered by country
            """
            results = client.search(query=query, country=country, max_results=max_results)
            return json.dumps(results, indent=2, default=str)
        
        @mcp.resource("perplexity://search/multi{?queries,max_results}")
        def multi_query_search_resource(queries: str, max_results: int = 5) -> str:
            """
            Perform a multi-query web search (up to 5 queries).
            
            URI: perplexity://search/multi{?queries,max_results}
            
            Args:
                queries: Comma-separated list of search queries (up to 5)
                max_results: Maximum number of results per query (1-20, default: 5)
            
            Returns:
                JSON string with grouped search results for each query
            """
            query_list = [q.strip() for q in queries.split(",")][:5]  # Limit to 5 queries
            results = client.search(query=query_list, max_results=max_results)
            return json.dumps(results, indent=2, default=str)
        
        @mcp.resource("perplexity://search/domain-filtered{?query,domains,max_results}")
        def domain_filtered_search_resource(query: str, domains: str, max_results: int = 10) -> str:
            """
            Perform a web search filtered by domain allowlist or denylist.
            
            URI: perplexity://search/domain-filtered{?query,domains,max_results}
            
            Args:
                query: Search query string
                domains: Comma-separated list of domains (allowlist) or domains with "-" prefix (denylist)
                         Example: "science.org,pnas.org,cell.com" or "-pinterest.com,-reddit.com"
                max_results: Maximum number of results (1-20, default: 10)
            
            Returns:
                JSON string with search results filtered by domains
            """
            domain_list = [d.strip() for d in domains.split(",")][:20]  # Limit to 20 domains
            results = client.search(
                query=query,
                search_domain_filter=domain_list,
                max_results=max_results
            )
            return json.dumps(results, indent=2, default=str)
        
        @mcp.resource("perplexity://search/language-filtered{?query,languages,max_results}")
        def language_filtered_search_resource(query: str, languages: str, max_results: int = 10) -> str:
            """
            Perform a web search filtered by language.
            
            URI: perplexity://search/language-filtered{?query,languages,max_results}
            
            Args:
                query: Search query string
                languages: Comma-separated list of ISO 639-1 language codes (e.g., "en,fr,de")
                max_results: Maximum number of results (1-20, default: 10)
            
            Returns:
                JSON string with search results filtered by languages
            """
            language_list = [l.strip() for l in languages.split(",")][:10]  # Limit to 10 languages
            results = client.search(
                query=query,
                search_language_filter=language_list,
                max_results=max_results
            )
            return json.dumps(results, indent=2, default=str)
        
        @mcp.resource("perplexity://search/advanced{?query,max_results,max_tokens,max_tokens_per_page,country,domains,languages,mode,recency}")
        def advanced_search_resource(
            query: str,
            max_results: int = 10,
            max_tokens: Optional[int] = None,
            max_tokens_per_page: int = 2048,
            country: Optional[str] = None,
            domains: Optional[str] = None,
            languages: Optional[str] = None,
            mode: Optional[str] = None,
            recency: Optional[str] = None,
        ) -> str:
            """
            Perform an advanced web search with multiple filtering options.
            
            URI: perplexity://search/advanced{?query,max_results,max_tokens,max_tokens_per_page,country,domains,languages,mode,recency}
            
            Args:
                query: Search query string
                max_results: Maximum number of results (1-20, default: 10)
                max_tokens: Total content budget across all results (default: 25000, max: 1000000)
                max_tokens_per_page: Content extracted per webpage (default: 2048)
                country: ISO 3166-1 alpha-2 country code (e.g., "US", "GB")
                domains: Comma-separated list of domains (allowlist) or domains with "-" prefix (denylist)
                languages: Comma-separated list of ISO 639-1 language codes (e.g., "en,fr,de")
                mode: Search mode - "web", "academic", or "sec"
                recency: Filter by recency - "hour", "day", "week", "month", "year"
            
            Returns:
                JSON string with search results using advanced filters
            """
            search_params = {
                "query": query,
                "max_results": max_results,
                "max_tokens_per_page": max_tokens_per_page,
            }
            
            if max_tokens is not None:
                search_params["max_tokens"] = max_tokens
            if country:
                search_params["country"] = country
            if domains:
                domain_list = [d.strip() for d in domains.split(",")][:20]
                search_params["search_domain_filter"] = domain_list
            if languages:
                language_list = [l.strip() for l in languages.split(",")][:10]
                search_params["search_language_filter"] = language_list
            if mode:
                search_params["search_mode"] = mode
            if recency:
                search_params["search_recency_filter"] = recency
            
            results = client.search(**search_params)
            return json.dumps(results, indent=2, default=str)


# Create module instance (required for registry pattern)
module = PerplexitySearchToolModule()
