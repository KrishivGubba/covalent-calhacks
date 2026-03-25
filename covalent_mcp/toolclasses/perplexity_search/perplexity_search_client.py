"""
Perplexity Search API Client - Wrapper for Perplexity Search operations via Lambda.

Proxies requests through the Perplexity Gateway Lambda to keep API keys secure.
"""
import os
import json
import urllib.request
import urllib.error
from typing import Optional, List, Union, Dict, Any
from dotenv import load_dotenv

load_dotenv()


class PerplexitySearchClient:
    """
    Perplexity Search API client that proxies through Lambda Gateway.
    
    Usage:
        client = PerplexitySearchClient()
        results = client.search(
            query="latest AI developments",
            max_results=5
        )
    """
    
    def __init__(self, gateway_url: Optional[str] = None, auth_token: Optional[str] = None):
        """
        Initialize Perplexity Search client.
        
        Args:
            gateway_url: Perplexity Gateway Lambda URL (or from PERPLEXITY_GATEWAY_URL env var)
            auth_token: Auth0 access token for authenticating with Lambda (optional for now)
        """
        self.gateway_url = gateway_url or os.getenv("PERPLEXITY_GATEWAY_URL", "")
        self.auth_token = auth_token
        
        if not self.gateway_url:
            raise ValueError(
                "Perplexity Gateway URL required. Set PERPLEXITY_GATEWAY_URL env var or pass gateway_url."
            )
    
    def set_auth_token(self, token: str) -> None:
        """Set the Auth0 access token for authenticating requests."""
        self.auth_token = token
    
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
        Perform a web search using Perplexity Search API via Lambda Gateway.
        
        Args:
            query: Search query (string) or list of queries for multi-query search
            max_results: Maximum number of results (1-20, default: 10)
            max_tokens: Total content budget across all results (default: 25000, max: 1000000)
            max_tokens_per_page: Content extracted per webpage (default: 2048)
            country: ISO 3166-1 alpha-2 country code for regional filtering (e.g., "US", "GB")
            search_domain_filter: List of domains to include (allowlist) or exclude (denylist with "-" prefix)
            search_language_filter: List of ISO 639-1 language codes (e.g., ["en", "fr", "de"])
            search_mode: Deprecated/unsupported by Perplexity /search; ignored by gateway if provided
            search_recency_filter: Filter by recency - "hour", "day", "week", "month", "year"
            search_after_date_filter: Filter results published after this date (YYYY-MM-DD)
            search_before_date_filter: Filter results published before this date (YYYY-MM-DD)
            last_updated_after_filter: Filter results last updated after this date (YYYY-MM-DD)
            last_updated_before_filter: Filter results last updated before this date (YYYY-MM-DD)
        
        Returns:
            Dict containing search results with 'results' list and 'id'
        """
        print("are we even here in perplexity_search_client.py?")
        # Build request payload for Lambda
        payload = {
            "query": query,
            "max_results": max_results,
            "max_tokens_per_page": max_tokens_per_page,
        }
        
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        if country:
            payload["country"] = country
        if search_domain_filter:
            payload["search_domain_filter"] = search_domain_filter
        if search_language_filter:
            payload["search_language_filter"] = search_language_filter
        if search_mode:
            payload["search_mode"] = search_mode
        if search_recency_filter:
            payload["search_recency_filter"] = search_recency_filter
        if search_after_date_filter:
            payload["search_after_date_filter"] = search_after_date_filter
        if search_before_date_filter:
            payload["search_before_date_filter"] = search_before_date_filter
        if last_updated_after_filter:
            payload["last_updated_after_filter"] = last_updated_after_filter
        if last_updated_before_filter:
            payload["last_updated_before_filter"] = last_updated_before_filter
        
        # Build headers
        headers = {
            "Content-Type": "application/json",
        }
        if self.auth_token:
            headers["Authorization"] = f"Bearer {self.auth_token}"
        
        # Call Lambda Gateway
        search_url = f"{self.gateway_url.rstrip('/')}/search"
        req_data = json.dumps(payload).encode("utf-8")
        
        has_auth = "Authorization" in headers
        auth_preview = headers.get("Authorization", "")[:30] + "..." if has_auth else "(none)"
        print(f"🔍 Perplexity POST {search_url}")
        print(f"   Auth: {auth_preview}")
        print(f"   Query: {payload.get('query', payload.get('queries', ''))}")
        
        try:
            req = urllib.request.Request(
                search_url,
                data=req_data,
                headers=headers,
                method="POST",
            )
            
            with urllib.request.urlopen(req, timeout=30) as response:
                result = json.loads(response.read().decode("utf-8"))
            
            # Process and normalize response
            # Lambda returns the raw Perplexity response, normalize it
            return self._normalize_response(result, query, max_results)
            
        except urllib.error.HTTPError as e:
            error_body = e.read().decode("utf-8")
            try:
                error_json = json.loads(error_body)
                raise RuntimeError(f"Perplexity search failed: {error_json.get('error_description', error_json.get('error', error_body))}")
            except json.JSONDecodeError:
                raise RuntimeError(f"Perplexity search failed: {error_body}")
        except urllib.error.URLError as e:
            raise RuntimeError(f"Failed to connect to Perplexity Gateway: {e}")
    
    def _normalize_response(self, result: Dict[str, Any], query: Union[str, List[str]], max_results: int) -> Dict[str, Any]:
        """Normalize the Lambda response to a consistent format."""
        # If Lambda returns results in expected format, use directly
        if "results" in result:
            # Normalize each result to have consistent fields
            normalized_results = []
            for r in result.get("results", []):
                normalized_results.append({
                    "title": r.get("title", ""),
                    "url": r.get("url", ""),
                    "snippet": r.get("snippet", r.get("content", "")),
                    "date": r.get("date"),
                    "last_updated": r.get("last_updated"),
                })
            
            return {
                "id": result.get("id"),
                "results": normalized_results,
                "query": query,
                "max_results": max_results,
                "server_time": result.get("server_time"),
            }
        
        # If Lambda returns error, propagate it
        if "error" in result:
            raise RuntimeError(f"Perplexity search failed: {result.get('error_description', result['error'])}")
        
        # Return as-is if format is unexpected
        return result
