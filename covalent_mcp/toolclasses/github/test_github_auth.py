"""
Quick test script for GitHub authentication.

Run this to verify your GitHub OAuth setup works:
    python3 -m covalent_mcp.toolclasses.github.test_github_auth
"""
import os
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from covalent_mcp.toolclasses.github.github_auth import GitHubAuth


def main():
    """Test GitHub authentication."""
    print("🧪 Testing GitHub Authentication\n")
    
    # Check environment variables
    client_id = os.getenv("GITHUB_CLIENT_ID")
    client_secret = os.getenv("GITHUB_CLIENT_SECRET")
    
    if not client_id:
        print("❌ GITHUB_CLIENT_ID not set in environment")
        print("   Set it in your .env file or export it:")
        print("   export GITHUB_CLIENT_ID=your_client_id")
        return 1
    
    if not client_secret:
        print("❌ GITHUB_CLIENT_SECRET not set in environment")
        print("   Set it in your .env file or export it:")
        print("   export GITHUB_CLIENT_SECRET=your_client_secret")
        return 1
    
    print(f"✅ Client ID found: {client_id[:10]}...")
    print(f"✅ Client Secret found: {client_secret[:10]}...\n")
    
    try:
        auth = GitHubAuth()
        print("🔐 Requesting access token via Device Flow...\n")
        token = auth.get_access_token(scope="repo")
        print(f"\n✅ Success! Token acquired: {token[:20]}...")
        print(f"   Token saved to: {auth.token_storage_path}")
        return 0
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
