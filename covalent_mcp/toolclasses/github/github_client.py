"""
GitHub API Client - REST wrapper for GitHub operations.

Provides methods for repo, issue, and PR operations.
"""
import requests
from typing import Optional, Dict, Any, List
from covalent_mcp.toolclasses.github.github_auth import GitHubAuth


class GitHubClient:
    """
    GitHub API client for repository, issue, and PR operations.
    
    Usage:
        auth = GitHubAuth(...)
        client = GitHubClient(auth)
        repo = client.create_repo("my-repo", private=False)
    """
    
    BASE_URL = "https://api.github.com"
    
    def __init__(self, auth: Optional[GitHubAuth] = None, access_token: Optional[str] = None):
        """
        Initialize GitHub client.
        
        Args:
            auth: GitHubAuth instance (will get token automatically)
            access_token: Direct access token (if auth not provided)
        """
        if auth:
            self.auth = auth
            self.access_token = None  # Will be fetched on first use
        elif access_token:
            self.auth = None
            self.access_token = access_token
        else:
            raise ValueError("Either auth or access_token must be provided")
    
    def _get_token(self) -> str:
        """Get access token (from auth or direct)."""
        if self.access_token:
            return self.access_token
        if self.auth:
            self.access_token = self.auth.get_access_token()
            return self.access_token
        raise RuntimeError("No access token available")
    
    def _request(self, method: str, endpoint: str, **kwargs) -> Dict[str, Any]:
        """Make authenticated request to GitHub API."""
        url = f"{self.BASE_URL}{endpoint}"
        headers = {
            "Authorization": f"token {self._get_token()}",
            "Accept": "application/vnd.github.v3+json"
        }
        headers.update(kwargs.pop("headers", {}))
        
        response = requests.request(method, url, headers=headers, **kwargs)
        response.raise_for_status()
        return response.json()
    
    # Repository operations
    
    def create_repo(
        self,
        name: str,
        owner: Optional[str] = None,
        private: bool = False,
        description: Optional[str] = None,
        auto_init: bool = False,
        gitignore_template: Optional[str] = None,
        license_template: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Create a new repository.
        
        Args:
            name: Repository name
            owner: Organization/user to create repo under (default: authenticated user)
            description: Repository description
            private: Whether repo should be private
            auto_init: Initialize with README
            gitignore_template: .gitignore template name (e.g., "Node", "Python")
            license_template: License template name (e.g., "mit", "apache-2.0")
        
        Returns:
            Repository data dict
        """
        data = {
            "name": name,
            "private": private,
            "auto_init": auto_init
        }
        if description:
            data["description"] = description
        if gitignore_template:
            data["gitignore_template"] = gitignore_template
        if license_template:
            data["license_template"] = license_template
        
        if owner:
            endpoint = f"/orgs/{owner}/repos"
        else:
            endpoint = "/user/repos"
        
        return self._request("POST", endpoint, json=data)
    
    def create_repo_from_template(
        self,
        template_owner: str,
        template_repo: str,
        name: str,
        owner: Optional[str] = None,
        private: bool = False,
        description: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Create a repository from a template.
        
        Args:
            template_owner: Owner of the template repository
            template_repo: Name of the template repository
            name: Name for the new repository
            owner: Organization/user to create repo under (default: authenticated user)
            private: Whether repo should be private
            description: Repository description
        
        Returns:
            Repository data dict
        """
        data = {
            "name": name,
            "private": private
        }
        if description:
            data["description"] = description
        
        endpoint = f"/repos/{template_owner}/{template_repo}/generate"
        return self._request("POST", endpoint, json=data)
    
    def get_repo(self, owner: str, repo: str) -> Dict[str, Any]:
        """
        Get repository information.
        
        Args:
            owner: Repository owner (user or org)
            repo: Repository name
        
        Returns:
            Repository data dict
        """
        return self._request("GET", f"/repos/{owner}/{repo}")
    
    def list_repos(
        self,
        owner: Optional[str] = None,
        type: str = "all"  # all, owner, member, public, private
    ) -> List[Dict[str, Any]]:
        """
        List repositories.
        
        Args:
            owner: User/org to list repos for (default: authenticated user)
            type: Type of repos to list (all, owner, member, public, private)
        
        Returns:
            List of repository dicts
        """
        if owner:
            endpoint = f"/users/{owner}/repos"
        else:
            endpoint = "/user/repos"
        
        params = {"type": type, "per_page": 100}
        return self._request("GET", endpoint, params=params)
    
    # Issue operations
    
    def create_issue(
        self,
        owner: str,
        repo: str,
        title: str,
        body: Optional[str] = None,
        labels: Optional[List[str]] = None,
        assignees: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Create an issue.
        
        Args:
            owner: Repository owner
            repo: Repository name
            title: Issue title
            body: Issue body/description
            labels: List of label names
            assignees: List of usernames to assign
        
        Returns:
            Issue data dict
        """
        data = {"title": title}
        if body:
            data["body"] = body
        if labels:
            data["labels"] = labels
        if assignees:
            data["assignees"] = assignees
        
        return self._request("POST", f"/repos/{owner}/{repo}/issues", json=data)
    
    # Pull Request operations
    
    def create_pull_request(
        self,
        owner: str,
        repo: str,
        title: str,
        head: str,
        base: str,
        body: Optional[str] = None,
        draft: bool = False
    ) -> Dict[str, Any]:
        """
        Create a pull request.
        
        Args:
            owner: Repository owner
            repo: Repository name
            title: PR title
            head: Branch to merge FROM (e.g., "feature-branch" or "user:branch" for forks)
            base: Branch to merge INTO (e.g., "main")
            body: PR description
            draft: Whether PR should be a draft
        
        Returns:
            Pull request data dict
        """
        data = {
            "title": title,
            "head": head,
            "base": base,
            "draft": draft
        }
        if body:
            data["body"] = body
        
        return self._request("POST", f"/repos/{owner}/{repo}/pulls", json=data)
    
    # Repository update operations
    
    def update_repo_description(self, owner: str, repo: str, description: str) -> Dict[str, Any]:
        """
        Update repository description.
        
        Args:
            owner: Repository owner
            repo: Repository name
            description: New description
        
        Returns:
            Updated repository data dict
        """
        data = {"description": description}
        return self._request("PATCH", f"/repos/{owner}/{repo}", json=data)
    
    def set_repo_topics(self, owner: str, repo: str, topics: List[str]) -> Dict[str, Any]:
        """
        Set repository topics.
        
        Args:
            owner: Repository owner
            repo: Repository name
            topics: List of topic names
        
        Returns:
            Response dict with topics
        """
        data = {"names": topics}
        return self._request("PUT", f"/repos/{owner}/{repo}/topics", json=data)
    
    def rename_default_branch(self, owner: str, repo: str, new_name: str) -> Dict[str, Any]:
        """
        Rename the default branch of a repository.
        
        Args:
            owner: Repository owner
            repo: Repository name
            new_name: New name for the default branch
        
        Returns:
            Response dict
        """
        # First get current default branch
        repo_data = self.get_repo(owner, repo)
        current_branch = repo_data["default_branch"]
        
        # Rename the branch
        data = {"new_name": new_name}
        return self._request("POST", f"/repos/{owner}/{repo}/branches/{current_branch}/rename", json=data)