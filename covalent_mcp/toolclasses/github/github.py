"""
GitHub MCP Tools - Repository, Issue, and PR operations.

Exposes GitHub operations as MCP tools for LLM agents.
"""
from typing import Optional, List
from covalent_mcp.toolclasses.base import MCPToolModule
from covalent_mcp.toolclasses.github.github_client import GitHubClient
from covalent_mcp.toolclasses.github.github_auth import GitHubAuth
from fastmcp import FastMCP


class GitHubToolModule(MCPToolModule):
    """
    GitHub tool module for repository, issue, and PR operations.
    
    Provides MCP tools for:
    - Creating/getting/listing repositories
    - Creating issues
    - Creating pull requests
    """
    
    def __init__(self):
        """Initialize GitHub tool module with auth and client."""
        self.auth = None  # Lazy initialization
        self.client = None
    
    def _ensure_client(self) -> GitHubClient:
        """Ensure GitHub client is initialized."""
        if self.client is None:
            self.auth = GitHubAuth()
            self.client = GitHubClient(self.auth)
        return self.client
    
    def register(self, mcp: FastMCP) -> None:
        """Register GitHub tools with MCP server."""
        client = self._ensure_client()
        
        @mcp.tool()
        def create_repo(
            name: str,
            owner: Optional[str] = None,
            private: bool = False,
            description: Optional[str] = None
        ) -> dict:
            """
            Create a new GitHub repository.
            
            Args:
                name: Repository name
                owner: Organization/user to create repo under (default: authenticated user)
                private: Whether repository should be private
                description: Repository description
            
            Returns:
                Repository information including URL and name
            """
            repo = client.create_repo(
                name=name,
                owner=owner,
                private=private,
                description=description
            )
            return {
                "success": True,
                "name": repo["name"],
                "full_name": repo["full_name"],
                "url": repo["html_url"],
                "private": repo["private"]
            }
        
        @mcp.tool()
        def get_repo(owner: str, repo: str) -> dict:
            """
            Get information about a GitHub repository.
            
            Args:
                owner: Repository owner (user or organization)
                repo: Repository name
            
            Returns:
                Repository information including description, stars, language, etc.
            """
            repo_data = client.get_repo(owner, repo)
            return {
                "name": repo_data["name"],
                "full_name": repo_data["full_name"],
                "url": repo_data["html_url"],
                "description": repo_data.get("description"),
                "private": repo_data["private"],
                "stars": repo_data["stargazers_count"],
                "language": repo_data.get("language"),
                "default_branch": repo_data["default_branch"]
            }
        
        @mcp.tool()
        def list_repos(owner: Optional[str] = None, type: str = "all") -> dict:
            """
            List GitHub repositories.
            
            Args:
                owner: User/org to list repos for (default: authenticated user)
                type: Type of repos (all, owner, member, public, private)
            
            Returns:
                List of repositories with names and URLs
            """
            repos = client.list_repos(owner=owner, type=type)
            return {
                "count": len(repos),
                "repos": [
                    {
                        "name": r["name"],
                        "full_name": r["full_name"],
                        "url": r["html_url"],
                        "private": r["private"],
                        "description": r.get("description")
                    }
                    for r in repos
                ]
            }
        
        @mcp.tool()
        def create_issue(
            owner: str,
            repo: str,
            title: str,
            body: Optional[str] = None,
            labels: Optional[List[str]] = None
        ) -> dict:
            """
            Create a GitHub issue.
            
            Args:
                owner: Repository owner
                repo: Repository name
                title: Issue title
                body: Issue description/body
                labels: List of label names to apply
            
            Returns:
                Issue information including number and URL
            """
            issue = client.create_issue(
                owner=owner,
                repo=repo,
                title=title,
                body=body,
                labels=labels
            )
            return {
                "success": True,
                "number": issue["number"],
                "title": issue["title"],
                "url": issue["html_url"],
                "state": issue["state"]
            }
        
        @mcp.tool()
        def create_pull_request(
            owner: str,
            repo: str,
            title: str,
            head: str,
            base: str,
            body: Optional[str] = None,
            draft: bool = False
        ) -> dict:
            """
            Create a GitHub pull request.
            
            Args:
                owner: Repository owner
                repo: Repository name
                title: PR title
                head: Branch to merge FROM (e.g., "feature-branch")
                base: Branch to merge INTO (e.g., "main")
                body: PR description
                draft: Whether PR should be created as draft
            
            Returns:
                Pull request information including number and URL
            """
            pr = client.create_pull_request(
                owner=owner,
                repo=repo,
                title=title,
                head=head,
                base=base,
                body=body,
                draft=draft
            )
            return {
                "success": True,
                "number": pr["number"],
                "title": pr["title"],
                "url": pr["html_url"],
                "state": pr["state"],
                "draft": pr["draft"]
            }


# Create module instance (required for registry pattern)
module = GitHubToolModule()
