"""GitHub large-context provider."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

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

    # Cap how many repos we pull per run. Sorted by recency so inactive repos drop
    # out first. Tune here if you start hitting rate limits or want wider coverage.
    MAX_REPOS = 25

    _GH_URL_RE = re.compile(
        r"https?://github\.com/(?P<owner>[\w.-]+)/(?P<repo>[\w.-]+)/(?P<kind>issues|pull)/(?P<number>\d+)"
    )
    _CROSS_REPO_ISSUE_RE = re.compile(
        r"(?<![\w/])(?P<owner>[A-Za-z0-9][\w.-]*)/(?P<repo>[A-Za-z0-9][\w.-]*)#(?P<number>\d+)"
    )
    _SAME_REPO_ISSUE_RE = re.compile(
        r"(?:(?P<verb>close[sd]?|fix(?:e[sd])?|resolve[sd]?)\s+)?#(?P<number>\d+)",
        re.IGNORECASE,
    )
    _JIRA_URL_RE = re.compile(
        r"https?://[\w.-]+\.atlassian\.net/browse/([A-Z][A-Z0-9]{1,9}-\d+)"
    )
    # Project keys: 2-10 uppercase alphanumerics starting with a letter, hyphen, digits.
    # Bounded by non-word chars so we don't pick up substrings of larger identifiers.
    _JIRA_KEY_RE = re.compile(r"(?<![\w-])([A-Z]{2}[A-Z0-9]{0,8}-\d+)(?![\w-])")
    _SLACK_URL_RE = re.compile(
        r"https?://[\w.-]+\.slack\.com/archives/([A-Z0-9]+)/p(\d+)"
    )
    _NOTION_URL_RE = re.compile(
        r"https?://(?:www\.)?notion\.so/[\w%/-]*?"
        r"([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}|[0-9a-fA-F]{32})"
    )
    _GDOC_URL_RE = re.compile(
        r"https?://docs\.google\.com/(?:document|spreadsheets|presentation|forms)/d/([A-Za-z0-9_-]{10,})"
    )
    _GDRIVE_URL_RE = re.compile(
        r"https?://drive\.google\.com/(?:file/d/|open\?id=)([A-Za-z0-9_-]{10,})"
    )
    _GCAL_URL_RE = re.compile(
        r"https?://(?:www\.)?google\.com/calendar/event\?eid=([A-Za-z0-9_-]+)"
    )
    _GMAIL_URL_RE = re.compile(
        r"https?://mail\.google\.com/mail/[^/]+/#[\w-]+/([A-Za-z0-9]+)"
    )

    def __init__(self, integration_dao: IntegrationDAO):
        self.integration_dao = integration_dao

    def fetch_delta(self, cursor: Optional[dict], since_ts: str) -> ProviderFetchResult:
        token = self.integration_dao.get_token("github")
        if not token or not token.get("access_token"):
            raise RuntimeError("GitHub integration is not connected")

        client = GitHubClient(token["access_token"])
        since = (cursor or {}).get("since") or since_ts

        all_repos = client.list_repos(type="all")
        sorted_repos = sorted(
            all_repos,
            key=lambda repo: repo.get("pushed_at") or repo.get("updated_at") or "",
            reverse=True,
        )
        selected_repos = sorted_repos[: self.MAX_REPOS]

        records: List[dict] = []
        for repo in selected_repos:
            owner_info = repo.get("owner") or {}
            owner = owner_info.get("login") or ""
            repo_name = repo.get("name") or ""
            if not owner or not repo_name:
                continue
            repo_key = f"{owner}/{repo_name}"
            issues = client.list_issues(owner, repo_name, state="open", since=since, per_page=25)
            pulls = client.list_pull_requests(owner, repo_name, state="open", sort="updated", direction="desc", per_page=25)
            records.append({
                "repo": repo,
                "repo_key": repo_key,
                "owner": owner,
                "owner_type": owner_info.get("type") or "User",
                "owner_html_url": owner_info.get("html_url"),
                "issues": issues,
                "pulls": pulls,
            })

        return ProviderFetchResult(
            records=records,
            next_cursor={"since": datetime.now(timezone.utc).isoformat()},
            metadata={
                "backfill_since": since,
                "repos_available": len(all_repos),
                "repos_synced": len(records),
                "repo_cap": self.MAX_REPOS,
            },
        )

    def build_snapshot(self, fetch_result: ProviderFetchResult, previous_snapshot: ProviderSnapshot | None = None) -> ProviderSnapshot:
        owner_containers: Dict[str, SnapshotContainer] = {}
        repo_containers: list[SnapshotContainer] = []
        entities: list[SnapshotEntity] = []
        people_map: Dict[str, SnapshotPerson] = {}
        cross_links: list[SnapshotCrossLink] = []
        seen_cross_links: set[tuple[str, str, str]] = set()

        for record in fetch_result.records:
            repo = record["repo"]
            repo_key = record["repo_key"]
            owner = record["owner"]
            owner_type = (record.get("owner_type") or "User").lower()
            owner_container_type = "organization" if owner_type == "organization" else "user"

            if owner and owner not in owner_containers:
                owner_containers[owner] = SnapshotContainer(
                    container_type=owner_container_type,
                    container_id=owner,
                    title=owner,
                    source_url=record.get("owner_html_url"),
                )

            repo_containers.append(
                SnapshotContainer(
                    container_type="repository",
                    container_id=repo_key,
                    title=repo_key,
                    summary=repo.get("description"),
                    parent_id=owner or None,
                    source_url=repo.get("html_url"),
                )
            )

            for pull in record.get("pulls", []):
                author = (pull.get("user") or {}).get("login")
                reviewers = [
                    reviewer.get("login")
                    for reviewer in pull.get("requested_reviewers", [])
                    if reviewer.get("login")
                ]
                labels = [label.get("name") for label in pull.get("labels", []) if label.get("name")]
                body = pull.get("body") or ""
                title_text = pull.get("title") or ""

                pr_external_id = f"{repo_key}#PR{pull.get('number')}"
                linked_issue_numbers = self._extract_body_issue_numbers(body)
                related_entities, pr_cross_links = self._extract_references(
                    f"{title_text}\n{body}",
                    source_entity_id=pr_external_id,
                    current_repo_key=repo_key,
                )

                entities.append(
                    SnapshotEntity(
                        entity_type="pull_request",
                        external_id=pr_external_id,
                        title=title_text or f"PR #{pull.get('number')}",
                        status=pull.get("state") or "open",
                        summary=body or title_text,
                        project=repo_key,
                        feature_tags=labels,
                        people=[person for person in [author, *reviewers] if person],
                        related_entities=related_entities,
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
                            "linked_issue_ids": linked_issue_numbers,
                        },
                    )
                )
                self._upsert_people(people_map, [author, *reviewers], pr_external_id)
                self._merge_cross_links(cross_links, seen_cross_links, pr_cross_links)

            for issue in record.get("issues", []):
                assignees = [
                    assignee.get("login")
                    for assignee in issue.get("assignees", [])
                    if assignee.get("login")
                ]
                labels = [label.get("name") for label in issue.get("labels", []) if label.get("name")]
                body = issue.get("body") or ""
                title_text = issue.get("title") or ""

                issue_external_id = f"{repo_key}#ISSUE{issue.get('number')}"
                linked_numbers = self._extract_body_issue_numbers(body)
                linked_pr_ids = [f"{repo_key}#PR{number}" for number in linked_numbers]
                related_entities, issue_cross_links = self._extract_references(
                    f"{title_text}\n{body}",
                    source_entity_id=issue_external_id,
                    current_repo_key=repo_key,
                )

                entities.append(
                    SnapshotEntity(
                        entity_type="issue",
                        external_id=issue_external_id,
                        title=title_text or f"Issue #{issue.get('number')}",
                        status=issue.get("state") or "open",
                        summary=body or title_text,
                        project=repo_key,
                        feature_tags=labels,
                        people=[person for person in assignees if person],
                        related_entities=related_entities,
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
                self._upsert_people(people_map, assignees, issue_external_id)
                self._merge_cross_links(cross_links, seen_cross_links, issue_cross_links)

        containers: list[SnapshotContainer] = list(owner_containers.values()) + repo_containers

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

    def _extract_body_issue_numbers(self, text: str) -> list[str]:
        if not text:
            return []
        scrubbed = self._CROSS_REPO_ISSUE_RE.sub(" ", text)
        scrubbed = self._GH_URL_RE.sub(" ", scrubbed)
        numbers: list[str] = []
        for match in self._SAME_REPO_ISSUE_RE.finditer(scrubbed):
            number = match.group("number")
            if number not in numbers:
                numbers.append(number)
        return numbers

    def _extract_references(
        self,
        text: str,
        *,
        source_entity_id: str,
        current_repo_key: str,
    ) -> Tuple[List[str], List[SnapshotCrossLink]]:
        if not text:
            return [], []

        related_ids: list[str] = []
        links: list[SnapshotCrossLink] = []
        seen: set[tuple[str, str]] = set()

        def add(target_id: str, relationship: str) -> None:
            if not target_id or target_id == source_entity_id:
                return
            key = (target_id, relationship)
            if key in seen:
                return
            seen.add(key)
            links.append(
                SnapshotCrossLink(
                    source_entity_id=source_entity_id,
                    target_entity_id=target_id,
                    relationship=relationship,
                )
            )
            if target_id not in related_ids:
                related_ids.append(target_id)

        for match in self._GH_URL_RE.finditer(text):
            kind = "PR" if match.group("kind") == "pull" else "ISSUE"
            target = f"{match.group('owner')}/{match.group('repo')}#{kind}{match.group('number')}"
            add(target, "references")

        for match in self._CROSS_REPO_ISSUE_RE.finditer(text):
            target = f"{match.group('owner')}/{match.group('repo')}#ISSUE{match.group('number')}"
            add(target, "references")

        scrubbed = self._CROSS_REPO_ISSUE_RE.sub(" ", text)
        scrubbed = self._GH_URL_RE.sub(" ", scrubbed)
        for match in self._SAME_REPO_ISSUE_RE.finditer(scrubbed):
            verb = (match.group("verb") or "").lower()
            relationship = "fixes" if verb else "references"
            target = f"{current_repo_key}#ISSUE{match.group('number')}"
            add(target, relationship)

        for match in self._JIRA_URL_RE.finditer(text):
            add(f"jira:{match.group(1)}", "references")
        for match in self._JIRA_KEY_RE.finditer(text):
            add(f"jira:{match.group(1)}", "references")

        for match in self._SLACK_URL_RE.finditer(text):
            channel = match.group(1)
            ts_raw = match.group(2)
            ts = f"{ts_raw[:-6]}.{ts_raw[-6:]}" if len(ts_raw) > 6 else ts_raw
            add(f"slack:{channel}:{ts}", "references")

        for match in self._NOTION_URL_RE.finditer(text):
            raw = match.group(1).replace("-", "").lower()
            add(f"notion:{raw}", "references")

        for match in self._GDOC_URL_RE.finditer(text):
            add(f"gdrive:{match.group(1)}", "references")
        for match in self._GDRIVE_URL_RE.finditer(text):
            add(f"gdrive:{match.group(1)}", "references")
        for match in self._GCAL_URL_RE.finditer(text):
            add(f"calendar:{match.group(1)}", "references")
        for match in self._GMAIL_URL_RE.finditer(text):
            add(f"gmail:{match.group(1)}", "references")

        return related_ids, links

    def _merge_cross_links(
        self,
        accumulator: list[SnapshotCrossLink],
        seen: set[tuple[str, str, str]],
        new_links: list[SnapshotCrossLink],
    ) -> None:
        for link in new_links:
            key = (link.source_entity_id, link.target_entity_id, link.relationship)
            if key in seen:
                continue
            seen.add(key)
            accumulator.append(link)

    def _upsert_people(
        self,
        people_map: Dict[str, SnapshotPerson],
        handles: List[Optional[str]],
        related_entity: str,
    ) -> None:
        for handle in handles:
            if not handle:
                continue
            person = people_map.get(handle)
            if person is None:
                person = SnapshotPerson(
                    identifier=handle,
                    display_name=handle,
                    role="github_user",
                    related_entities=[],
                )
                people_map[handle] = person
            if related_entity not in person.related_entities:
                person.related_entities.append(related_entity)
