"""
GitHub MCP Tools - Repository, Issue, and PR operations.

Exposes GitHub operations as MCP tools for LLM agents.
Token is managed by the server via OAuth flow - MCP reads token from database.
"""
import json
import os
from pathlib import Path
from typing import Dict, Optional, List
from covalent_mcp.toolclasses.base import (
    MCPToolModule,
    ToolDisplaySchema,
    DisplayField,
    PassableOutput,
)
from covalent_mcp.toolclasses.github.github_client import GitHubClient
from fastmcp import FastMCP


def _get_db_path() -> Path:
    """Get path to the graph.db database."""
    # Prefer GRAPH_DB_PATH env var (set by Tauri in production)
    if os.getenv("GRAPH_DB_PATH"):
        db_path = Path(os.getenv("GRAPH_DB_PATH"))
        if db_path.exists():
            return db_path

    # Fall back to dev-relative path
    db_path = Path(__file__).parent.parent.parent.parent / "context-engine" / "graph.db"
    if db_path.exists():
        return db_path
    
    raise FileNotFoundError(
        "Database not found. Ensure graph.db exists in context-engine/ "
        "or set GRAPH_DB_PATH environment variable."
    )


class GitHubToolModule(MCPToolModule):
    """
    GitHub tool module for repository, issue, and PR operations.
    
    Provides MCP tools for:
    - Creating/getting/listing repositories
    - Creating issues
    - Creating pull requests
    """
    
    def __init__(self):
        """Initialize GitHub tool module."""
        self._client = None
        self._dao = None
    
    def _get_dao(self):
        """Get IntegrationDAO instance."""
        if self._dao is None:
            from server.integration_dao import IntegrationDAO
            db_path = _get_db_path()
            self._dao = IntegrationDAO(str(db_path))
        return self._dao
    
    def _ensure_client(self) -> GitHubClient:
        """Ensure GitHub client is initialized with a fresh token from database."""
        dao = self._get_dao()
        token_data = dao.get_token("github")
        
        if not token_data or not token_data.get("access_token"):
            raise RuntimeError(
                "No GitHub token found in database. "
                "Please authenticate via the server's OAuth flow first."
            )
        
        token = token_data["access_token"]
        if self._client is None:
            self._client = GitHubClient(access_token=token)
        else:
            self._client.access_token = token
        return self._client
    
    def register(self, mcp: FastMCP) -> None:
        """Register GitHub tools with MCP server."""
        tool_module = self
        
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
            client = tool_module._ensure_client()
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
            client = tool_module._ensure_client()
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
            client = tool_module._ensure_client()
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
            client = tool_module._ensure_client()
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
            client = tool_module._ensure_client()
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
            client = tool_module._ensure_client()
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
            client = tool_module._ensure_client()
            result = client.rename_default_branch(owner, repo, new_name)
            return {
                "success": True,
                "message": f"Default branch renamed to {new_name}",
                "new_name": new_name
            }
    
    def get_display_schemas(self) -> Dict[str, ToolDisplaySchema]:
        """Return display schemas for GitHub tools."""
        return {
            "create_repo": ToolDisplaySchema(
                tool_name="create_repo",
                display_name="Create GitHub Repository",
                description="Create a new GitHub repository.",
                fields=[
                    DisplayField(key="name", label="Repository Name", required=True, widget="text_input", placeholder="my-new-repo"),
                    DisplayField(key="description", label="Description", widget="textarea", placeholder="A short description..."),
                    DisplayField(key="private", label="Private", widget="toggle"),
                    DisplayField(key="owner", label="Owner / Org", widget="text_input", placeholder="Leave blank for your account"),
                    DisplayField(key="auto_init", label="Initialize with README", widget="toggle"),
                    DisplayField(key="license_template", label="License", widget="text_input", placeholder="e.g. mit, apache-2.0"),
                ],
                passable_outputs=[
                    PassableOutput(key="name", description="The repository name"),
                    PassableOutput(key="full_name", description="Full name (owner/repo)"),
                    PassableOutput(key="url", description="URL to the repository"),
                ],
            ),
            "create_repo_from_template": ToolDisplaySchema(
                tool_name="create_repo_from_template",
                display_name="Create Repo from Template",
                description="Create a new repository from a template.",
                fields=[
                    DisplayField(key="template_owner", label="Template Owner", required=True, widget="text_input"),
                    DisplayField(key="template_repo", label="Template Repo", required=True, widget="text_input"),
                    DisplayField(key="name", label="New Repo Name", required=True, widget="text_input"),
                    DisplayField(key="description", label="Description", widget="textarea"),
                    DisplayField(key="private", label="Private", widget="toggle"),
                ],
            ),
            "create_issue": ToolDisplaySchema(
                tool_name="create_issue",
                display_name="Create GitHub Issue",
                description="Create a new issue in a GitHub repository.",
                fields=[
                    DisplayField(key="owner", label="Repo Owner", required=True, widget="text_input"),
                    DisplayField(key="repo", label="Repository", required=True, widget="text_input"),
                    DisplayField(key="title", label="Issue Title", required=True, widget="text_input"),
                    DisplayField(key="body", label="Description", widget="textarea", placeholder="Describe the issue..."),
                    DisplayField(key="labels", label="Labels", widget="email_list", placeholder="Add labels..."),
                ],
                passable_outputs=[
                    PassableOutput(key="number", description="The issue number"),
                    PassableOutput(key="url", description="URL to the issue"),
                ],
            ),
            "create_pull_request": ToolDisplaySchema(
                tool_name="create_pull_request",
                display_name="Create Pull Request",
                description="Open a new pull request.",
                fields=[
                    DisplayField(key="owner", label="Repo Owner", required=True, widget="text_input"),
                    DisplayField(key="repo", label="Repository", required=True, widget="text_input"),
                    DisplayField(key="title", label="PR Title", required=True, widget="text_input"),
                    DisplayField(key="head", label="From Branch", required=True, widget="text_input"),
                    DisplayField(key="base", label="Into Branch", required=True, widget="text_input", placeholder="main"),
                    DisplayField(key="body", label="Description", widget="textarea"),
                    DisplayField(key="draft", label="Draft PR", widget="toggle"),
                ],
                passable_outputs=[
                    PassableOutput(key="number", description="The PR number"),
                    PassableOutput(key="url", description="URL to the pull request"),
                ],
            ),
            "update_repo_description": ToolDisplaySchema(
                tool_name="update_repo_description",
                display_name="Update Repo Description",
                description="Update a repository's description.",
                fields=[
                    DisplayField(key="owner", label="Repo Owner", required=True, widget="text_input"),
                    DisplayField(key="repo", label="Repository", required=True, widget="text_input"),
                    DisplayField(key="description", label="New Description", required=True, widget="textarea"),
                ],
            ),
            "set_repo_topics": ToolDisplaySchema(
                tool_name="set_repo_topics",
                display_name="Set Repo Topics",
                description="Set topic tags on a repository.",
                fields=[
                    DisplayField(key="owner", label="Repo Owner", required=True, widget="text_input"),
                    DisplayField(key="repo", label="Repository", required=True, widget="text_input"),
                    DisplayField(key="topics", label="Topics", widget="email_list", placeholder="Add topics..."),
                ],
            ),
            "rename_default_branch": ToolDisplaySchema(
                tool_name="rename_default_branch",
                display_name="Rename Default Branch",
                description="Rename the default branch of a repository.",
                fields=[
                    DisplayField(key="owner", label="Repo Owner", required=True, widget="text_input"),
                    DisplayField(key="repo", label="Repository", required=True, widget="text_input"),
                    DisplayField(key="new_name", label="New Branch Name", required=True, widget="text_input", placeholder="main"),
                ],
            ),
        }

    def register_resources(self, mcp: FastMCP) -> None:
        """Register GitHub resources (read-only operations) with MCP server."""
        tool_module = self
        
        @mcp.resource("github://repo/{owner}/{repo}")
        def get_repo_resource(owner: str, repo: str) -> str:
            """
            Get information about a GitHub repository.
            
            URI: github://repo/{owner}/{repo}
            """
            client = tool_module._ensure_client()
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
        
        @mcp.resource("github://repos{?type}")
        def list_repos_resource(type: str = "all") -> str:
            """
            List repositories for the authenticated user.
            
            URI: github://repos{?type}
            Optional query param: type - "all", "owner", "member", "public", "private" (default: "all")
            """
            client = tool_module._ensure_client()
            repos = client.list_repos(type=type)
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
            client = tool_module._ensure_client()
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
