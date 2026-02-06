#!/usr/bin/env python3
"""
Test script to verify Perplexity Gateway Lambda is working.
Tests both the health endpoint (no auth) and search endpoint (requires Auth0 JWT).

Usage:
    # Test health only (no auth needed):
    python tests/test_perplexity_gateway.py --health-only
    
    # Test with auth (requires valid Auth0 token):
    python tests/test_perplexity_gateway.py --token "your_auth0_jwt_token"
    
    # Use a specific gateway URL:
    python tests/test_perplexity_gateway.py --url "https://your-gateway.amazonaws.com"
"""
import os
import sys
import json
import argparse
import urllib.request
import urllib.error

# Default gateway URLs (from Terraform output)
DEFAULT_API_GATEWAY_URL = "https://cf5guf9iba.execute-api.us-east-1.amazonaws.com"
DEFAULT_FUNCTION_URL = "https://iavgkblfbjfbq7i3h4nhbj54ey0egtfm.lambda-url.us-east-1.on.aws"


def test_health(base_url: str) -> dict:
    """Test the health endpoint (no auth required)."""
    print("\n--- Testing Health Endpoint ---")
    url = f"{base_url.rstrip('/')}/health"
    print(f"  URL: {url}")
    
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=15) as response:
            data = json.loads(response.read().decode("utf-8"))
            print(f"✓ Health check passed!")
            print(f"  Status: {data.get('status', 'unknown')}")
            print(f"  Service: {data.get('service', 'unknown')}")
            print(f"  Perplexity configured: {data.get('perplexity_configured', False)}")
            print(f"  Auth0 configured: {data.get('auth0_configured', False)}")
            return {"success": True, "data": data}
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8")
        print(f"✗ Health check failed: {e.code}")
        print(f"  Error: {error_body}")
        return {"success": False, "error": error_body, "code": e.code}
    except Exception as e:
        print(f"✗ Health check error: {e}")
        return {"success": False, "error": str(e)}


def test_search_unauthorized(base_url: str) -> dict:
    """Test that search endpoint rejects requests without auth."""
    print("\n--- Testing Search (No Auth - Should Reject) ---")
    url = f"{base_url.rstrip('/')}/search"
    
    try:
        req_data = json.dumps({"query": "test"}).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=req_data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=15) as response:
            # Should not reach here - we expect a 401
            data = json.loads(response.read().decode("utf-8"))
            print(f"✗ Unexpected success - endpoint should require auth!")
            return {"success": False, "error": "Endpoint did not require auth"}
    except urllib.error.HTTPError as e:
        if e.code == 401:
            print(f"✓ Correctly rejected with 401 Unauthorized")
            return {"success": True, "message": "Auth correctly required"}
        else:
            error_body = e.read().decode("utf-8")
            print(f"✗ Unexpected error: {e.code} - {error_body}")
            return {"success": False, "error": error_body, "code": e.code}
    except Exception as e:
        print(f"✗ Request error: {e}")
        return {"success": False, "error": str(e)}


def test_search_with_auth(base_url: str, auth_token: str, query: str = "What is the weather in San Francisco?") -> dict:
    """Test search endpoint with valid auth."""
    print("\n--- Testing Search (With Auth) ---")
    url = f"{base_url.rstrip('/')}/search"
    print(f"  URL: {url}")
    print(f"  Query: {query[:50]}..." if len(query) > 50 else f"  Query: {query}")
    
    try:
        req_data = json.dumps({
            "query": query,
            "max_results": 5,
        }).encode("utf-8")
        
        req = urllib.request.Request(
            url,
            data=req_data,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {auth_token}",
            },
            method="POST",
        )
        
        with urllib.request.urlopen(req, timeout=30) as response:
            data = json.loads(response.read().decode("utf-8"))
            print(f"✓ Search successful!")
            
            # Display results based on Perplexity API response format
            if "results" in data:
                print(f"  Found {len(data['results'])} result(s)")
                for i, result in enumerate(data["results"][:3]):
                    title = result.get("title", result.get("url", "Untitled"))
                    print(f"  {i+1}. {title[:60]}...")
            elif "answer" in data:
                answer = data["answer"]
                print(f"  Answer: {answer[:200]}..." if len(answer) > 200 else f"  Answer: {answer}")
            else:
                print(f"  Response keys: {list(data.keys())}")
            
            return {"success": True, "data": data}
            
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8")
        print(f"✗ Search failed: {e.code}")
        try:
            error_json = json.loads(error_body)
            print(f"  Error: {error_json.get('error', 'unknown')}")
            print(f"  Details: {error_json.get('error_description', error_body)}")
        except:
            print(f"  Error: {error_body}")
        return {"success": False, "error": error_body, "code": e.code}
    except Exception as e:
        print(f"✗ Search error: {e}")
        return {"success": False, "error": str(e)}


def main():
    parser = argparse.ArgumentParser(description="Test Perplexity Gateway Lambda")
    parser.add_argument("--url", default=DEFAULT_API_GATEWAY_URL,
                        help=f"Gateway URL (default: {DEFAULT_API_GATEWAY_URL})")
    parser.add_argument("--token", help="Auth0 JWT token for authenticated endpoints")
    parser.add_argument("--health-only", action="store_true",
                        help="Only test health endpoint (no auth needed)")
    parser.add_argument("--query", default="What are the latest developments in AI?",
                        help="Search query to test")
    parser.add_argument("--function-url", action="store_true",
                        help="Use Lambda Function URL instead of API Gateway")
    
    args = parser.parse_args()
    
    # Choose URL
    if args.function_url:
        base_url = DEFAULT_FUNCTION_URL
    else:
        base_url = args.url
    
    print("=" * 60)
    print("Perplexity Gateway Test")
    print("=" * 60)
    print(f"\nGateway URL: {base_url}")
    
    results = {}
    
    # Test health (always)
    results["health"] = test_health(base_url)
    
    if args.health_only:
        print("\n(Skipping auth tests - use --token to test search)")
    else:
        # Test that unauthenticated requests are rejected
        results["unauth"] = test_search_unauthorized(base_url)
        
        # Test authenticated search
        if args.token:
            results["search"] = test_search_with_auth(base_url, args.token, args.query)
        else:
            print("\n--- Skipping Authenticated Search ---")
            print("  Provide --token to test authenticated search")
            print("  You can get a token from your app's sessionStorage:")
            print("    sessionStorage.getItem('auth0_access_token')")
    
    # Summary
    print("\n" + "=" * 60)
    print("Summary")
    print("=" * 60)
    
    passed = sum(1 for r in results.values() if r.get("success"))
    total = len(results)
    print(f"\n{passed}/{total} tests passed")
    
    if not results.get("health", {}).get("success"):
        print("\n⚠️  Health check failed - Lambda may not be deployed yet")
        print("   Run: gh workflow run deploy-lambda.yml")
        return 1
    
    if passed == total:
        print("\n✓ All tests passed!")
        return 0
    else:
        return 1


if __name__ == "__main__":
    sys.exit(main())
