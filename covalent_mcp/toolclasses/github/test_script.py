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
    print("📦 TEST: List Repositories (Resource)")
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
    print(f"📂 TEST: Get Repository Info (Resource) - {owner}/{repo}")
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


def test_create_repo(name: str, private: bool = False, description: str = None, auto_init: bool = True):
    """Test: Create a new repository (creates real repo!)."""
    print("=" * 60)
    print(f"➕ TEST: Create Repository - {name}")
    print("=" * 60)
    
    repo = client.create_repo(
        name=name,
        private=private,
        description=description,
        auto_init=auto_init,
        gitignore_template="Python",  # Use Python .gitignore
        license_template="mit"  # Use MIT license
    )
    print(f"✅ Created repo: {repo['html_url']}")
    print(f"   Name: {repo['name']}")
    print(f"   Full name: {repo['full_name']}")
    print(f"   Private: {repo['private']}")
    print()
    
    return repo


def test_create_repo_from_template(template_owner: str, template_repo: str, name: str, description: str = None):
    """Test: Create repo from template (creates real repo!)."""
    print("=" * 60)
    print(f"📋 TEST: Create Repository from Template - {name}")
    print("=" * 60)
    
    repo = client.create_repo_from_template(
        template_owner=template_owner,
        template_repo=template_repo,
        name=name,
        private=False,
        description=description
    )
    print(f"✅ Created repo from template: {repo['html_url']}")
    print(f"   Name: {repo['name']}")
    print(f"   Full name: {repo['full_name']}")
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


def test_update_repo_description(owner: str, repo: str, description: str):
    """Test: Update repository description."""
    print("=" * 60)
    print(f"📝 TEST: Update Repository Description - {owner}/{repo}")
    print("=" * 60)
    
    repo_data = client.update_repo_description(owner, repo, description)
    print(f"✅ Updated description: {repo_data['html_url']}")
    print(f"   New description: {repo_data.get('description', 'None')}")
    print()
    
    return repo_data


def test_set_repo_topics(owner: str, repo: str, topics: list):
    """Test: Set repository topics."""
    print("=" * 60)
    print(f"🏷️  TEST: Set Repository Topics - {owner}/{repo}")
    print("=" * 60)
    
    result = client.set_repo_topics(owner, repo, topics)
    print(f"✅ Set topics: {', '.join(result.get('names', topics))}")
    print()
    
    return result


def test_rename_default_branch(owner: str, repo: str, new_name: str):
    """Test: Rename default branch (renames real branch!)."""
    print("=" * 60)
    print(f"🌿 TEST: Rename Default Branch - {owner}/{repo}")
    print("=" * 60)
    
    result = client.rename_default_branch(owner, repo, new_name)
    print(f"✅ Renamed default branch to: {new_name}")
    print()
    
    return result


# ============================================================================
# TEST FLOW - Sequential workflow using the same repo
# ============================================================================

if __name__ == "__main__":
    # Replace with your actual GitHub username
    MY_USERNAME = "KrishivGubba"  # CHANGE THIS!
    
    # Test repo name (will be created if it doesn't exist)
    TEST_REPO_NAME = "mcp-test-repo"
    
    print("\n" + "=" * 60)
    print("🚀 GITHUB MCP TOOLS - TEST FLOW")
    print("=" * 60 + "\n")
    
    try:
        # Step 1: List your repos (Resource)
        print("STEP 1: Listing your repositories...\n")
        repos = test_list_repos()
        
        # Step 2: Check if test repo already exists
        print("STEP 2: Checking if test repo exists...\n")
        test_repo_exists = False
        test_repo_owner = None
        
        for repo in repos:
            if repo['name'] == TEST_REPO_NAME:
                test_repo_exists = True
                test_repo_owner = repo['full_name'].split('/')[0]
                print(f"✅ Test repo '{TEST_REPO_NAME}' already exists!")
                print(f"   URL: {repo['html_url']}\n")
                break
        
        # Step 3: Create test repo if it doesn't exist
        if not test_repo_exists:
            print(f"STEP 3: Creating test repo '{TEST_REPO_NAME}'...\n")
            new_repo = test_create_repo(
                name=TEST_REPO_NAME,
                private=False,
                description="Test repository for MCP GitHub tools",
                auto_init=True
            )
            test_repo_owner = new_repo['full_name'].split('/')[0]
        else:
            print(f"STEP 3: Using existing repo '{TEST_REPO_NAME}'...\n")
            test_repo_owner = MY_USERNAME
        
        # Step 4: Get repo info (Resource)
        print("STEP 4: Getting repository info...\n")
        repo_info = test_get_repo(test_repo_owner, TEST_REPO_NAME)
        
        # Step 5: Update repo description
        print("STEP 5: Updating repository description...\n")
        test_update_repo_description(
            owner=test_repo_owner,
            repo=TEST_REPO_NAME,
            description="Updated: Test repository for MCP GitHub tools - Updated via API"
        )
        
        # Step 6: Set repo topics
        print("STEP 6: Setting repository topics...\n")
        test_set_repo_topics(
            owner=test_repo_owner,
            repo=TEST_REPO_NAME,
            topics=["mcp", "test", "automation", "github-api"]
        )
        
        # Step 7: Create an issue
        print("STEP 7: Creating an issue...\n")
        test_create_issue(
            owner=test_repo_owner,
            repo=TEST_REPO_NAME,
            title="Test Issue from MCP Tools",
            body="This is a test issue created via the GitHub MCP tools!",
            labels=["test", "mcp"]
        )
        
        # Step 8: Optional - Rename default branch (commented out by default)
        # Uncomment if you want to test branch renaming
        # print("STEP 8: Renaming default branch...\n")
        # test_rename_default_branch(
        #     owner=test_repo_owner,
        #     repo=TEST_REPO_NAME,
        #     new_name="main"  # or "master" or whatever you want
        # )
        
        print("\n" + "=" * 60)
        print("✅ TEST FLOW COMPLETED SUCCESSFULLY!")
        print("=" * 60)
        print(f"\n📦 Test repo: https://github.com/{test_repo_owner}/{TEST_REPO_NAME}")
        print("   You can check it out on GitHub!\n")
        
    except Exception as e:
        print("\n" + "=" * 60)
        print("❌ TEST FLOW FAILED")
        print("=" * 60)
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()
