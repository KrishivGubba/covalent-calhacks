"""
Perplexity Search API Client - Wrapper for Perplexity Search operations.

Provides methods for web search with filtering and content extraction.
"""
import os
from typing import Optional, List, Union, Dict, Any
from perplexity import Perplexity
from dotenv import load_dotenv

load_dotenv()


class PerplexitySearchClient:
    """
    Perplexity Search API client for web search operations.
    
    Usage:
        client = PerplexitySearchClient()
        results = client.search(
            query="latest AI developments",
            max_results=5
        )
    """
    
    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize Perplexity Search client.
        
        Args:
            api_key: Perplexity API key (or from PERPLEXITY_API_KEY env var)
        """
        self.api_key = api_key or os.getenv("PERPLEXITY_API_KEY")
        if not self.api_key:
            raise ValueError(
                "Perplexity API key required. Set PERPLEXITY_API_KEY env var or pass api_key."
            )
        self.client = Perplexity(api_key=self.api_key)
    
    def search(
        self,
        query: Union[str, List[str]],
        max_results: int = 10,
        max_tokens: Optional[int] = None,
        max_tokens_per_page: int = 2048,
        country: Optional[str] = None,
        search_domain_filter: Optional[List[str]] = None,
        search_language_filter: Optional[List[str]] = None,
        search_mode: Optional[str] = None,
        search_recency_filter: Optional[str] = None,
        search_after_date_filter: Optional[str] = None,
        search_before_date_filter: Optional[str] = None,
        last_updated_after_filter: Optional[str] = None,
        last_updated_before_filter: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Perform a web search using Perplexity Search API.
        
        Args:
            query: Search query (string) or list of queries for multi-query search
            max_results: Maximum number of results (1-20, default: 10)
            max_tokens: Total content budget across all results (default: 25000, max: 1000000)
            max_tokens_per_page: Content extracted per webpage (default: 2048)
            country: ISO 3166-1 alpha-2 country code for regional filtering (e.g., "US", "GB")
            search_domain_filter: List of domains to include (allowlist) or exclude (denylist with "-" prefix)
            search_language_filter: List of ISO 639-1 language codes (e.g., ["en", "fr", "de"])
            search_mode: Search mode - "web", "academic", or "sec"
            search_recency_filter: Filter by recency - "hour", "day", "week", "month", "year"
            search_after_date_filter: Filter results published after this date (YYYY-MM-DD)
            search_before_date_filter: Filter results published before this date (YYYY-MM-DD)
            last_updated_after_filter: Filter results last updated after this date (YYYY-MM-DD)
            last_updated_before_filter: Filter results last updated before this date (YYYY-MM-DD)
        
        Returns:
            Dict containing search results with 'results' list and 'id'
        """
        # Build search parameters
        params = {
            "query": query,
            "max_results": max_results,
            "max_tokens_per_page": max_tokens_per_page,
        }
        
        if max_tokens is not None:
            params["max_tokens"] = max_tokens
        if country:
            params["country"] = country
        if search_domain_filter:
            params["search_domain_filter"] = search_domain_filter
        if search_language_filter:
            params["search_language_filter"] = search_language_filter
        if search_mode:
            params["search_mode"] = search_mode
        if search_recency_filter:
            params["search_recency_filter"] = search_recency_filter
        if search_after_date_filter:
            params["search_after_date_filter"] = search_after_date_filter
        if search_before_date_filter:
            params["search_before_date_filter"] = search_before_date_filter
        if last_updated_after_filter:
            params["last_updated_after_filter"] = last_updated_after_filter
        if last_updated_before_filter:
            params["last_updated_before_filter"] = last_updated_before_filter
        
        # Perform search
        search_response = self.client.search.create(**params)
        
        # Convert response to dict format.
        # In the current SDK, results are always a flat list of Result objects,
        # even when you pass a list of queries. We just normalize them to
        # simple dicts; multi-query calls will return a single flat list.
        results_data = []
        for result in search_response.results:
            results_data.append(
                {
                    "title": result.title,
                    "url": result.url,
                    "snippet": result.snippet,
                    "date": getattr(result, "date", None),
                    "last_updated": getattr(result, "last_updated", None),
                }
            )
        
        return {
            "id": getattr(search_response, "id", None),
            "results": results_data,
            "query": query,
            "max_results": max_results,
            "server_time": getattr(search_response, "server_time", None),
        }
