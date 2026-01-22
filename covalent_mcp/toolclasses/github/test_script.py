import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from covalent_mcp.toolclasses.github.github_auth import GitHubAuth
from covalent_mcp.toolclasses.github.github_client import GitHubClient


# Initialize client (shared across all tests)
auth = GitHubAuth()
client = GitHubClient(auth)


def test_list_repos():
    """Test: List all your repositories (read-only, safe)."""
    print("=" * 60)
    print("📦 TEST: List Repositories")
    print("=" * 60)
    
    repos = client.list_repos()
    print(f"Found {len(repos)} repositories\n")
    
    for i, repo in enumerate(repos[:10], 1):  # Show first 10
        print(f"{i}. {repo['full_name']}")
        print(f"   URL: {repo['html_url']}")
        print(f"   Private: {repo['private']}")
        if repo.get('description'):
            print(f"   Description: {repo['description']}")
        print()
    
    return repos


def test_get_repo(owner: str, repo: str):
    """Test: Get info about a specific repository (read-only, safe)."""
    print("=" * 60)
    print(f"📂 TEST: Get Repository Info - {owner}/{repo}")
    print("=" * 60)
    
    repo_info = client.get_repo(owner, repo)
    print(f"Repository: {repo_info['full_name']}")
    print(f"URL: {repo_info['html_url']}")
    print(f"Stars: {repo_info['stargazers_count']}")
    print(f"Language: {repo_info.get('language', 'N/A')}")
    print(f"Default branch: {repo_info['default_branch']}")
    print(f"Private: {repo_info['private']}")
    if repo_info.get('description'):
        print(f"Description: {repo_info['description']}")
    print()
    
    return repo_info


def test_create_repo(name: str, private: bool = False, description: str = None):
    """Test: Create a new repository (creates real repo!)."""
    print("=" * 60)
    print(f"➕ TEST: Create Repository - {name}")
    print("=" * 60)
    
    repo = client.create_repo(
        name=name,
        private=private,
        description=description
    )
    print(f"✅ Created repo: {repo['html_url']}")
    print(f"   Name: {repo['name']}")
    print(f"   Full name: {repo['full_name']}")
    print(f"   Private: {repo['private']}")
    print()
    
    return repo


def test_create_issue(owner: str, repo: str, title: str, body: str = None, labels: list = None):
    """Test: Create an issue (creates real issue!)."""
    print("=" * 60)
    print(f"🐛 TEST: Create Issue - {owner}/{repo}")
    print("=" * 60)
    
    issue = client.create_issue(
        owner=owner,
        repo=repo,
        title=title,
        body=body,
        labels=labels
    )
    print(f"✅ Created issue: {issue['html_url']}")
    print(f"   Number: #{issue['number']}")
    print(f"   Title: {issue['title']}")
    print(f"   State: {issue['state']}")
    print()
    
    return issue


def test_create_pr(owner: str, repo: str, title: str, head: str, base: str, body: str = None, draft: bool = False):
    """Test: Create a pull request (creates real PR!)."""
    print("=" * 60)
    print(f"🔀 TEST: Create Pull Request - {owner}/{repo}")
    print("=" * 60)
    
    pr = client.create_pull_request(
        owner=owner,
        repo=repo,
        title=title,
        head=head,
        base=base,
        body=body,
        draft=draft
    )
    print(f"✅ Created PR: {pr['html_url']}")
    print(f"   Number: #{pr['number']}")
    print(f"   Title: {pr['title']}")
    print(f"   State: {pr['state']}")
    print(f"   Draft: {pr['draft']}")
    print()
    
    return pr


# ============================================================================
# TEST RUNNER - Uncomment the tests you want to run
# ============================================================================

if __name__ == "__main__":
    # Replace with your actual GitHub username
    MY_USERNAME = "KrishivGubba"
    
    # ===== SAFE TESTS (read-only) =====
    
    # Test 1: List your repos
    # repos = test_list_repos()
    
    # Test 2: Get info about a specific repo (replace with your repo)
    # test_get_repo(MY_USERNAME, "coldsend")
    
    # ===== DESTRUCTIVE TESTS (creates real stuff!) =====
    
    # Test 3: Create a new repo
    # test_create_repo("test-repo-from-mcp", private=True, description="Testing MCP tools")
    # import time
    # time.sleep(10)
    # # Test 4: Create an issue (requires existing repo)
    # test_create_issue(
    #     owner=MY_USERNAME,
    #     repo="test-repo-from-mcp",
    #     title="Test Issue from MCP",
    #     body="This is a test issue! go fuck yourself"
    # )
    
    # Test 5: Create a PR (requires existing repo with branches)
    test_create_pr(
        owner=MY_USERNAME,
        repo="some-existing-repo",
        title="Test PR from MCP",
        head="feature-branch",  # Branch to merge FROM
        base="main",             # Branch to merge INTO
        body="This is a test PR!"
    )