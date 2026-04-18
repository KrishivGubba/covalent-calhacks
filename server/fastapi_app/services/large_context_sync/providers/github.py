"""GitHub large-context provider."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Dict, List, Optional

from covalent_mcp.toolclasses.github.github_client import GitHubClient
from server.integration_dao import IntegrationDAO

from ..models import (
    ProviderFetchResult,
    ProviderSnapshot,
    SnapshotContainer,
    SnapshotCrossLink,
    SnapshotEntity,
    SnapshotPerson,
)
from .base import LargeContextProvider


class GitHubLargeContextProvider(LargeContextProvider):
    provider_id = "github"
    display_name = "GitHub"
    supports_live_sync = True
    file_name = "github.md"
    integration_provider_key = "github"

    def __init__(self, integration_dao: IntegrationDAO):
        self.integration_dao = integration_dao

    def fetch_delta(self, cursor: Optional[dict], since_ts: str) -> ProviderFetchResult:
        token = self.integration_dao.get_token("github")
        if not token or not token.get("access_token"):
            raise RuntimeError("GitHub integration is not connected")

        client = GitHubClient(token["access_token"])
        since = (cursor or {}).get("since") or since_ts
        repos = client.list_repos(type="all")[:10]
        records: List[dict] = []
        for repo in repos:
            owner = repo.get("owner", {}).get("login") or ""
            repo_name = repo.get("name") or ""
            if not owner or not repo_name:
                continue
            repo_key = f"{owner}/{repo_name}"
            issues = client.list_issues(owner, repo_name, state="open", since=since, per_page=25)
            pulls = client.list_pull_requests(owner, repo_name, state="open", sort="updated", direction="desc", per_page=25)
            records.append({
                "repo": repo,
                "repo_key": repo_key,
                "issues": issues,
                "pulls": pulls,
            })
        return ProviderFetchResult(
            records=records,
            next_cursor={"since": datetime.now(timezone.utc).isoformat()},
            metadata={"backfill_since": since},
        )

    def build_snapshot(self, fetch_result: ProviderFetchResult, previous_snapshot: ProviderSnapshot | None = None) -> ProviderSnapshot:
        containers: list[SnapshotContainer] = []
        entities: list[SnapshotEntity] = []
        people_map: Dict[str, SnapshotPerson] = {}
        cross_links: list[SnapshotCrossLink] = []

        for record in fetch_result.records:
            repo = record["repo"]
            repo_key = record["repo_key"]
            containers.append(
                SnapshotContainer(
                    container_type="repository",
                    container_id=repo_key,
                    title=repo_key,
                    summary=repo.get("description"),
                    source_url=repo.get("html_url"),
                )
            )

            for pull in record.get("pulls", []):
                author = (pull.get("user") or {}).get("login")
                reviewers = [reviewer.get("login") for reviewer in pull.get("requested_reviewers", []) if reviewer.get("login")]
                labels = [label.get("name") for label in pull.get("labels", []) if label.get("name")]
                linked_issue_ids = self._extract_linked_issue_ids(pull.get("body", ""))
                entities.append(
                    SnapshotEntity(
                        entity_type="pull_request",
                        external_id=f"{repo_key}#PR{pull.get('number')}",
                        title=pull.get("title") or f"PR #{pull.get('number')}",
                        status=pull.get("state") or "open",
                        summary=pull.get("body") or pull.get("title") or "",
                        project=repo_key,
                        feature_tags=labels,
                        people=[person for person in [author, *reviewers] if person],
                        related_entities=[f"{repo_key}#ISSUE{number}" for number in linked_issue_ids],
                        updated_at=pull.get("updated_at"),
                        source_url=pull.get("html_url"),
                        container_id=repo_key,
                        extra_fields={
                            "repo": repo_key,
                            "number": pull.get("number"),
                            "author": author or "",
                            "reviewers": reviewers,
                            "labels": labels,
                            "base_branch": ((pull.get("base") or {}).get("ref") or ""),
                            "head_branch": ((pull.get("head") or {}).get("ref") or ""),
                            "linked_issue_ids": linked_issue_ids,
                        },
                    )
                )
                self._upsert_people(people_map, [author, *reviewers], f"{repo_key}#PR{pull.get('number')}")
                for issue_number in linked_issue_ids:
                    cross_links.append(
                        SnapshotCrossLink(
                            source_entity_id=f"{repo_key}#PR{pull.get('number')}",
                            target_entity_id=f"{repo_key}#ISSUE{issue_number}",
                            relationship="references",
                        )
                    )

            for issue in record.get("issues", []):
                assignees = [assignee.get("login") for assignee in issue.get("assignees", []) if assignee.get("login")]
                labels = [label.get("name") for label in issue.get("labels", []) if label.get("name")]
                linked_pr_ids = self._extract_linked_pr_ids(issue.get("body", ""), repo_key)
                entities.append(
                    SnapshotEntity(
                        entity_type="issue",
                        external_id=f"{repo_key}#ISSUE{issue.get('number')}",
                        title=issue.get("title") or f"Issue #{issue.get('number')}",
                        status=issue.get("state") or "open",
                        summary=issue.get("body") or issue.get("title") or "",
                        project=repo_key,
                        feature_tags=labels,
                        people=[person for person in assignees if person],
                        related_entities=linked_pr_ids,
                        updated_at=issue.get("updated_at"),
                        source_url=issue.get("html_url"),
                        container_id=repo_key,
                        extra_fields={
                            "repo": repo_key,
                            "number": issue.get("number"),
                            "assignees": assignees,
                            "labels": labels,
                            "milestone": ((issue.get("milestone") or {}).get("title") or ""),
                            "linked_pr_ids": linked_pr_ids,
                        },
                    )
                )
                self._upsert_people(people_map, assignees, f"{repo_key}#ISSUE{issue.get('number')}")

        return ProviderSnapshot(
            provider_id=self.provider_id,
            provider_display_name=self.display_name,
            generated_at=datetime.now(timezone.utc).isoformat(),
            cursor=fetch_result.next_cursor,
            metadata=fetch_result.metadata,
            containers=containers,
            entities=entities,
            relevant_people=sorted(people_map.values(), key=lambda person: person.display_name.lower()),
            cross_links=cross_links,
        )

    def _extract_linked_issue_ids(self, body: str) -> list[str]:
        linked_numbers: list[str] = []
        for token in body.replace(",", " ").split():
            if token.startswith("#") and token[1:].isdigit():
                linked_numbers.append(token[1:])
        return linked_numbers

    def _extract_linked_pr_ids(self, body: str, repo_key: str) -> list[str]:
        return [f"{repo_key}#PR{number}" for number in self._extract_linked_issue_ids(body)]

    def _upsert_people(self, people_map: Dict[str, SnapshotPerson], handles: List[Optional[str]], related_entity: str) -> None:
        for handle in handles:
            if not handle:
                continue
            person = people_map.get(handle)
            if person is None:
                person = SnapshotPerson(identifier=handle, display_name=handle, role="github_user", related_entities=[])
                people_map[handle] = person
            if related_entity not in person.related_entities:
                person.related_entities.append(related_entity)
