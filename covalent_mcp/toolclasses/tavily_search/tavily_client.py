"""
Tavily Search API Client - thin wrapper around the `tavily-python` SDK.

Reads the API key from the `TAVILY_API_KEY` env var.
"""
import os
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv

load_dotenv()


class TavilySearchClient:
    """
    Tavily Search API client.

    Usage:
        client = TavilySearchClient()
        results = client.search(query="latest AI news", max_results=5)
    """

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("TAVILY_API_KEY", "")
        if not self.api_key:
            raise ValueError(
                "TAVILY_API_KEY env var not set. Add it to your .env or pass api_key=..."
            )
        # Import lazily so the MCP server can still start if the SDK isn't installed.
        from tavily import TavilyClient  # type: ignore
        self._client = TavilyClient(self.api_key)

    def search(
        self,
        query: str,
        search_depth: str = "fast",
        max_results: int = 5,
        topic: Optional[str] = None,
        days: Optional[int] = None,
        include_domains: Optional[List[str]] = None,
        exclude_domains: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Run a Tavily search and return the raw response dict.

        Args:
            query: Search query string.
            search_depth: "fast" (sub-second, default) or "advanced" (broader synthesis).
            max_results: Upper bound on result count.
            topic: Optional topic mode, e.g. "general" or "news".
            days: For `topic="news"`, how many days back to search.
            include_domains: Restrict results to these domains.
            exclude_domains: Exclude these domains from results.
        """
        params: Dict[str, Any] = {
            "query": query,
            "search_depth": search_depth,
            "max_results": max_results,
        }
        if topic:
            params["topic"] = topic
        if days is not None:
            params["days"] = days
        if include_domains:
            params["include_domains"] = include_domains
        if exclude_domains:
            params["exclude_domains"] = exclude_domains

        return self._client.search(**params)
