"""
Simple test script for PerplexitySearchClient.

Run this from the project root (with venv active):

    export PERPLEXITY_API_KEY="your_key"  # or use .env
    python -m covalent_mcp.toolclasses.perplexity_search.test_script
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict

from dotenv import load_dotenv

from covalent_mcp.toolclasses.perplexity_search.perplexity_search_client import (
    PerplexitySearchClient,
)


def pretty_print(title: str, payload: Dict[str, Any]) -> None:
    print(f"\n=== {title} ===")
    print(json.dumps(payload, indent=2, default=str))


def main() -> None:
    # Load .env if present
    load_dotenv()

    if not os.getenv("PERPLEXITY_API_KEY"):
        raise RuntimeError(
            "PERPLEXITY_API_KEY is not set. "
            "Set it in your environment or .env before running this script."
        )

    client = PerplexitySearchClient()

    # 1) Basic search
    basic = client.search(
        query="latest AI developments 2024",
        max_results=3,
        max_tokens_per_page=512,
    )
    pretty_print("Basic search", basic)

    # 2) Regional search example (US news)
    regional = client.search(
        query="government policies on renewable energy",
        country="US",
        max_results=3,
    )
    pretty_print("Regional search (US)", regional)

    # 3) Domain-filtered search example (allowlist)
    domain_filtered = client.search(
        query="climate change research",
        search_domain_filter=["science.org", "pnas.org", "cell.com"],
        max_results=3,
    )
    pretty_print("Domain-filtered search (science.org/pnas.org/cell.com)", domain_filtered)

    # 4) Multi-query search example
    multi = client.search(
        query=[
            "artificial intelligence trends 2024",
            "machine learning breakthroughs recent",
        ],
        max_results=2,
    )
    pretty_print("Multi-query search", multi)


if __name__ == "__main__":
    main()

