"""Jira MCP tools."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from covalent_mcp.toolclasses.base import DisplayField, MCPToolModule, PassableOutput, ToolDisplaySchema
from covalent_mcp.toolclasses.jira.auth import get_jira_connection
from covalent_mcp.toolclasses.jira.jira_client import JiraClient
from fastmcp import FastMCP


class JiraToolModule(MCPToolModule):
    def __init__(self):
        self.client: Optional[JiraClient] = None

    def _ensure_client(self) -> tuple[JiraClient, Dict[str, Any]]:
        token_data, metadata = get_jira_connection(require_configured=True)
        token = token_data["access_token"]
        cloud_id = metadata.get("cloud_id") or metadata.get("site_id")
        if self.client is None or self.client.access_token != token or self.client.cloud_id != cloud_id:
            self.client = JiraClient(access_token=token, cloud_id=cloud_id)
        return self.client, metadata

    def get_display_schemas(self) -> Dict[str, ToolDisplaySchema]:
        return {
            "create_jira_issue": ToolDisplaySchema(
                tool_name="create_jira_issue",
                display_name="Create Jira Ticket",
                description="Create a new issue in Jira.",
                fields=[
                    DisplayField(key="project_key", label="Project Key", required=True, widget="text_input"),
                    DisplayField(key="summary", label="Summary", required=True, widget="text_input"),
                    DisplayField(key="issue_type", label="Issue Type", required=True, widget="text_input", placeholder="Task"),
                    DisplayField(key="description", label="Description", widget="textarea"),
                    DisplayField(key="assignee_account_id", label="Assignee Account ID", widget="text_input"),
                    DisplayField(key="priority", label="Priority", widget="text_input", placeholder="High"),
                ],
                passable_outputs=[
                    PassableOutput(key="issue_key", description="The created Jira issue key"),
                    PassableOutput(key="url", description="URL to the created Jira issue"),
                ],
            ),
            "update_jira_issue": ToolDisplaySchema(
                tool_name="update_jira_issue",
                display_name="Update Jira Ticket",
                description="Update editable fields on a Jira issue.",
                fields=[
                    DisplayField(key="issue_key", label="Issue Key", required=True, editable=False, widget="display_text"),
                    DisplayField(key="summary", label="Summary", widget="text_input"),
                    DisplayField(key="description", label="Description", widget="textarea"),
                    DisplayField(key="priority", label="Priority", widget="text_input"),
                    DisplayField(key="fields_json", label="Additional Fields (JSON)", widget="textarea"),
                ],
            ),
            "assign_jira_issue": ToolDisplaySchema(
                tool_name="assign_jira_issue",
                display_name="Assign Jira Ticket",
                description="Assign a Jira issue to a user account.",
                fields=[
                    DisplayField(key="issue_key", label="Issue Key", required=True, editable=False, widget="display_text"),
                    DisplayField(key="account_id", label="Account ID", required=True, widget="text_input"),
                ],
            ),
            "add_jira_comment": ToolDisplaySchema(
                tool_name="add_jira_comment",
                display_name="Comment on Jira Ticket",
                description="Add a comment to a Jira issue.",
                fields=[
                    DisplayField(key="issue_key", label="Issue Key", required=True, editable=False, widget="display_text"),
                    DisplayField(key="comment", label="Comment", required=True, widget="textarea"),
                ],
            ),
            "transition_jira_issue": ToolDisplaySchema(
                tool_name="transition_jira_issue",
                display_name="Transition Jira Ticket",
                description="Move a Jira issue through its workflow.",
                fields=[
                    DisplayField(key="issue_key", label="Issue Key", required=True, editable=False, widget="display_text"),
                    DisplayField(key="transition_id", label="Transition ID", required=True, widget="text_input"),
                ],
            ),
        }

    def register(self, mcp: FastMCP) -> None:
        module = self

        @mcp.tool()
        def list_jira_projects() -> dict:
            client, _ = module._ensure_client()
            projects = client.list_projects()
            return {
                "success": True,
                "projects": [
                    {
                        "id": project.get("id"),
                        "key": project.get("key"),
                        "name": project.get("name"),
                        "projectTypeKey": project.get("projectTypeKey"),
                    }
                    for project in projects
                ],
            }

        @mcp.tool()
        def list_jira_issue_types() -> dict:
            client, _ = module._ensure_client()
            issue_types = client.list_issue_types()
            return {
                "success": True,
                "issue_types": [
                    {
                        "id": issue_type.get("id"),
                        "name": issue_type.get("name"),
                        "description": issue_type.get("description"),
                    }
                    for issue_type in issue_types
                ],
            }

        @mcp.tool()
        def search_jira_issues(
            jql: Optional[str] = None,
            project_key: Optional[str] = None,
            status: Optional[str] = None,
            max_results: int = 25,
        ) -> dict:
            client, metadata = module._ensure_client()
            clauses: List[str] = []
            if jql:
                clauses.append(f"({jql})")
            if project_key:
                clauses.append(f'project = "{project_key}"')
            elif metadata.get("project_keys"):
                allowed = ", ".join(f'"{key}"' for key in metadata["project_keys"])
                clauses.append(f"project in ({allowed})")
            if status:
                clauses.append(f'status = "{status}"')
            effective_jql = " AND ".join(clauses) if clauses else "order by updated DESC"
            results = client.search_issues(
                effective_jql,
                max_results=max_results,
                fields=["summary", "status", "assignee", "reporter", "priority", "issuetype", "project", "updated"],
            )
            return {
                "success": True,
                "issues": [
                    {
                        "issue_key": issue.get("key"),
                        "summary": (issue.get("fields") or {}).get("summary"),
                        "status": ((issue.get("fields") or {}).get("status") or {}).get("name"),
                        "project_key": (((issue.get("fields") or {}).get("project") or {}).get("key")),
                        "url": f"{metadata.get('site_url', '').rstrip('/')}/browse/{issue.get('key')}",
                    }
                    for issue in results.get("issues", [])
                ],
            }

        @mcp.tool()
        def get_jira_issue(issue_key: str) -> dict:
            client, metadata = module._ensure_client()
            issue = client.get_issue(
                issue_key,
                fields=["summary", "description", "status", "assignee", "reporter", "priority", "issuetype", "project", "comment", "updated", "created"],
                expand=["names"],
            )
            fields = issue.get("fields") or {}
            return {
                "success": True,
                "issue_key": issue.get("key"),
                "summary": fields.get("summary"),
                "description": JiraClient.adf_to_text(fields.get("description")),
                "status": (fields.get("status") or {}).get("name"),
                "project_key": ((fields.get("project") or {}).get("key")),
                "priority": ((fields.get("priority") or {}).get("name")),
                "issue_type": ((fields.get("issuetype") or {}).get("name")),
                "url": f"{metadata.get('site_url', '').rstrip('/')}/browse/{issue.get('key')}",
                "comments": [
                    JiraClient.adf_to_text(comment.get("body"))
                    for comment in ((fields.get("comment") or {}).get("comments") or [])
                ],
            }

        @mcp.tool()
        def create_jira_issue(
            project_key: str,
            summary: str,
            issue_type: str,
            description: Optional[str] = None,
            assignee_account_id: Optional[str] = None,
            priority: Optional[str] = None,
        ) -> dict:
            client, metadata = module._ensure_client()
            fields: Dict[str, Any] = {
                "project": {"key": project_key},
                "summary": summary,
                "issuetype": {"name": issue_type},
            }
            if description:
                fields["description"] = JiraClient.plain_text_to_adf(description)
            if assignee_account_id:
                fields["assignee"] = {"accountId": assignee_account_id}
            if priority:
                fields["priority"] = {"name": priority}
            created = client.create_issue(fields)
            issue_key = created.get("key")
            return {
                "success": True,
                "issue_key": issue_key,
                "id": created.get("id"),
                "url": f"{metadata.get('site_url', '').rstrip('/')}/browse/{issue_key}",
            }

        @mcp.tool()
        def update_jira_issue(
            issue_key: str,
            summary: Optional[str] = None,
            description: Optional[str] = None,
            priority: Optional[str] = None,
            fields_json: Optional[str] = None,
        ) -> dict:
            client, metadata = module._ensure_client()
            fields: Dict[str, Any] = {}
            if summary:
                fields["summary"] = summary
            if description is not None:
                fields["description"] = JiraClient.plain_text_to_adf(description)
            if priority:
                fields["priority"] = {"name": priority}
            if fields_json:
                fields.update(json.loads(fields_json))
            client.update_issue(issue_key, fields)
            return {
                "success": True,
                "issue_key": issue_key,
                "url": f"{metadata.get('site_url', '').rstrip('/')}/browse/{issue_key}",
            }

        @mcp.tool()
        def assign_jira_issue(issue_key: str, account_id: str) -> dict:
            client, metadata = module._ensure_client()
            client.assign_issue(issue_key, account_id)
            return {
                "success": True,
                "issue_key": issue_key,
                "account_id": account_id,
                "url": f"{metadata.get('site_url', '').rstrip('/')}/browse/{issue_key}",
            }

        @mcp.tool()
        def add_jira_comment(issue_key: str, comment: str) -> dict:
            client, metadata = module._ensure_client()
            comment_result = client.add_comment(issue_key, JiraClient.plain_text_to_adf(comment))
            return {
                "success": True,
                "issue_key": issue_key,
                "comment_id": comment_result.get("id"),
                "url": f"{metadata.get('site_url', '').rstrip('/')}/browse/{issue_key}",
            }

        @mcp.tool()
        def list_jira_transitions(issue_key: str) -> dict:
            client, _ = module._ensure_client()
            transitions = client.list_transitions(issue_key)
            return {
                "success": True,
                "transitions": [
                    {
                        "id": transition.get("id"),
                        "name": transition.get("name"),
                        "to_status": ((transition.get("to") or {}).get("name")),
                    }
                    for transition in transitions
                ],
            }

        @mcp.tool()
        def transition_jira_issue(issue_key: str, transition_id: str) -> dict:
            client, metadata = module._ensure_client()
            client.transition_issue(issue_key, transition_id)
            return {
                "success": True,
                "issue_key": issue_key,
                "transition_id": transition_id,
                "url": f"{metadata.get('site_url', '').rstrip('/')}/browse/{issue_key}",
            }


jira_module = JiraToolModule()
