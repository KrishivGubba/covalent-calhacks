"""
GitHub MCP Tools - Repository, Issue, and PR operations.

Exposes GitHub operations as MCP tools for LLM agents.
"""
import json
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
            description: Optional[str] = None,
            auto_init: bool = False,
            gitignore_template: Optional[str] = None,
            license_template: Optional[str] = None
        ) -> dict:
            """
            Create a new GitHub repository.
            
            Args:
                name: Repository name
                owner: Organization/user to create repo under (default: authenticated user)
                private: Whether repository should be private
                description: Repository description
                auto_init: Initialize with README
                gitignore_template: .gitignore template name (e.g., "Node", "Python")
                license_template: License template name (e.g., "mit", "apache-2.0")
            
            Returns:
                Repository information including URL and name
            """
            repo = client.create_repo(
                name=name,
                owner=owner,
                private=private,
                description=description,
                auto_init=auto_init,
                gitignore_template=gitignore_template,
                license_template=license_template
            )
            return {
                "success": True,
                "name": repo["name"],
                "full_name": repo["full_name"],
                "url": repo["html_url"],
                "private": repo["private"]
            }
        
        @mcp.tool()
        def create_repo_from_template(
            template_owner: str,
            template_repo: str,
            name: str,
            owner: Optional[str] = None,
            private: bool = False,
            description: Optional[str] = None
        ) -> dict:
            """
            Create a new GitHub repository from a template repository.
            
            Args:
                template_owner: Owner of the template repository
                template_repo: Name of the template repository
                name: Name for the new repository
                owner: Organization/user to create repo under (default: authenticated user)
                private: Whether repository should be private
                description: Repository description
            
            Returns:
                Repository information including URL and name
            """
            repo = client.create_repo_from_template(
                template_owner=template_owner,
                template_repo=template_repo,
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
        
        @mcp.tool()
        def update_repo_description(owner: str, repo: str, description: str) -> dict:
            """
            Update the description of an existing GitHub repository.
            
            Args:
                owner: Repository owner
                repo: Repository name
                description: New description
            
            Returns:
                Updated repository information
            """
            repo_data = client.update_repo_description(owner, repo, description)
            return {
                "success": True,
                "name": repo_data["name"],
                "full_name": repo_data["full_name"],
                "url": repo_data["html_url"],
                "description": repo_data.get("description")
            }
        
        @mcp.tool()
        def set_repo_topics(owner: str, repo: str, topics: List[str]) -> dict:
            """
            Set topics (tags) for an existing GitHub repository.
            
            Args:
                owner: Repository owner
                repo: Repository name
                topics: List of topic names (e.g., ["python", "api", "web"])
            
            Returns:
                Response with topics that were set
            """
            result = client.set_repo_topics(owner, repo, topics)
            return {
                "success": True,
                "topics": result.get("names", topics)
            }
        
        @mcp.tool()
        def rename_default_branch(owner: str, repo: str, new_name: str) -> dict:
            """
            Rename the default branch of an existing GitHub repository.
            
            Args:
                owner: Repository owner
                repo: Repository name
                new_name: New name for the default branch (e.g., "main", "master")
            
            Returns:
                Response indicating success
            """
            result = client.rename_default_branch(owner, repo, new_name)
            return {
                "success": True,
                "message": f"Default branch renamed to {new_name}",
                "new_name": new_name
            }
    
    def register_resources(self, mcp: FastMCP) -> None:
        """Register GitHub resources (read-only operations) with MCP server."""
        client = self._ensure_client()
        
        @mcp.resource("github://repo/{owner}/{repo}")
        def get_repo_resource(owner: str, repo: str) -> str:
            """
            Get information about a GitHub repository.
            
            URI: github://repo/{owner}/{repo}
            """
            repo_data = client.get_repo(owner, repo)
            return json.dumps({
                "name": repo_data["name"],
                "full_name": repo_data["full_name"],
                "url": repo_data["html_url"],
                "description": repo_data.get("description"),
                "private": repo_data["private"],
                "stars": repo_data["stargazers_count"],
                "language": repo_data.get("language"),
                "default_branch": repo_data["default_branch"]
            }, indent=2)
        
        @mcp.resource("github://repos")
        def list_repos_resource() -> str:
            """
            List repositories for the authenticated user.
            
            URI: github://repos
            """
            repos = client.list_repos()
            return json.dumps({
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
            }, indent=2)
        
        @mcp.resource("github://repos/{owner}")
        def list_repos_by_owner_resource(owner: str) -> str:
            """
            List repositories for a specific user or organization.
            
            URI: github://repos/{owner}
            """
            repos = client.list_repos(owner=owner)
            return json.dumps({
                "count": len(repos),
                "owner": owner,
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
            }, indent=2)


# Create module instance (required for registry pattern)
module = GitHubToolModule()
