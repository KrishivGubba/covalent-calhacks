"""
Tavily Search MCP Resources - fast web search operations.

Exposes the Tavily Search API as MCP resources (read-only) for LLM agents.

Tavily returns in <1 second and is the DEFAULT fast-search resource. Use
`perplexity://...` only when deep multi-source synthesis is actually needed.
"""
import json
from typing import Optional

from fastmcp import FastMCP

from covalent_mcp.toolclasses.base import MCPToolModule
from covalent_mcp.toolclasses.tavily_search.tavily_client import TavilySearchClient


class TavilySearchToolModule(MCPToolModule):
    """
    Tavily Search module for fast web search operations.

    All functions are registered as MCP **resources** (read-only).

    Provides MCP resources for:
      - Basic fast web search
      - Advanced web search with domain filters, topic, and recency
    """

    def __init__(self):
        self._client: Optional[TavilySearchClient] = None

    def _ensure_client(self) -> TavilySearchClient:
        """Lazily construct the Tavily client (so import never fails on missing env)."""
        if self._client is None:
            self._client = TavilySearchClient()
        return self._client

    def register(self, mcp: FastMCP) -> None:
        """No write tools - Tavily is read-only, all surface is via resources."""
        pass

    def register_resources(self, mcp: FastMCP) -> None:
        """Register Tavily Search resources with MCP server."""
        tool_module = self

        @mcp.resource("tavily://search/{query}")
        def tavily_search(query: str, max_results: int = 5) -> str:
            """
            Fast web search via Tavily (sub-second).

            PREFER THIS for general lookups: emails, phone numbers, dates, facts,
            identifiers, URLs, current events. Use `perplexity://search/...` only
            when you need deep, multi-source synthesis (it takes 15+ seconds).

            URI: tavily://search/{query}

            Args:
                query: Search query string.
                max_results: Maximum number of results (1-20, default: 5).

            Returns:
                JSON string with search results including titles, URLs, and snippets.
            """
            client = tool_module._ensure_client()
            results = client.search(
                query=query, search_depth="fast", max_results=max_results,
            )
            return json.dumps(results, indent=2, default=str)

        @mcp.resource(
            "tavily://search/advanced/{query}"
            "{?topic,days,include_domains,exclude_domains,max_results}"
        )
        def tavily_search_advanced(
            query: str,
            topic: Optional[str] = None,
            days: Optional[int] = None,
            include_domains: Optional[str] = None,
            exclude_domains: Optional[str] = None,
            max_results: int = 5,
        ) -> str:
            """
            Advanced Tavily search with domain filters and news topic mode.

            Still fast; still preferred over `perplexity://` for most lookups.

            URI: tavily://search/advanced/{query}

            Args:
                query: Search query string.
                topic: Optional topic mode - "general" or "news".
                days: For `topic="news"`, how many days back to search.
                include_domains: Comma-separated list of domains to restrict to.
                exclude_domains: Comma-separated list of domains to exclude.
                max_results: Maximum number of results (1-20, default: 5).

            Returns:
                JSON string with filtered search results.
            """
            client = tool_module._ensure_client()
            include_list = (
                [d.strip() for d in include_domains.split(",") if d.strip()]
                if include_domains else None
            )
            exclude_list = (
                [d.strip() for d in exclude_domains.split(",") if d.strip()]
                if exclude_domains else None
            )
            results = client.search(
                query=query,
                search_depth="advanced",
                max_results=max_results,
                topic=topic,
                days=days,
                include_domains=include_list,
                exclude_domains=exclude_list,
            )
            return json.dumps(results, indent=2, default=str)


module = TavilySearchToolModule()
