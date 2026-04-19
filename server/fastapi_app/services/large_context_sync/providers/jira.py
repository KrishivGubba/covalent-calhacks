"""Jira large-context provider."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, Optional

from covalent_mcp.toolclasses.issue_tracker.common import extract_external_references
from covalent_mcp.toolclasses.jira.auth import get_jira_connection
from covalent_mcp.toolclasses.jira.jira_client import JiraClient
from logger import get_logger
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

log = get_logger()


class JiraLargeContextProvider(LargeContextProvider):
    provider_id = "jira"
    display_name = "Jira"
    supports_live_sync = True
    file_name = "jira.md"
    integration_provider_key = "jira"

    SEARCH_FIELDS = [
        "summary",
        "description",
        "status",
        "assignee",
        "reporter",
        "priority",
        "issuetype",
        "project",
        "updated",
        "created",
        "comment",
        "parent",
    ]

    def __init__(self, integration_dao: IntegrationDAO):
        self.integration_dao = integration_dao

    def is_connected(self, integration_dao) -> bool:
        token = integration_dao.get_token("jira")
        if not token:
            return False
        metadata = token.get("provider_metadata") or {}
        cloud_id = metadata.get("cloud_id") or metadata.get("site_id")
        project_keys = metadata.get("project_keys") or []
        return bool(cloud_id and project_keys)

    def fetch_delta(self, cursor, since_ts: str) -> ProviderFetchResult:
        token_data, metadata = get_jira_connection(self.integration_dao, require_configured=True)
        cloud_id = metadata.get("cloud_id") or metadata.get("site_id")
        project_keys = metadata.get("project_keys") or []
        since = (cursor or {}).get("since") or since_ts
        client = JiraClient(token_data["access_token"], cloud_id=cloud_id)

        issues_by_key: dict[str, dict[str, Any]] = {}
        since_for_jql = self._format_jql_datetime(since)
        log.info(
            f"Jira large-context fetch starting for site={metadata.get('site_name') or cloud_id} "
            f"projects={project_keys} since={since}"
        )
        for project_key in project_keys:
            queries = [
                f'project = "{project_key}" AND statusCategory != Done ORDER BY updated DESC',
                f'project = "{project_key}" AND updated >= "{since_for_jql}" ORDER BY updated DESC',
            ]
            for query in queries:
                response = client.search_issues(
                    query,
                    max_results=50,
                    fields=self.SEARCH_FIELDS,
                    expand=["names"],
                )
                for issue in response.get("issues", []):
                    issues_by_key[issue["key"]] = issue

        detailed_issues = [
            client.get_issue(
                issue_key,
                fields=self.SEARCH_FIELDS,
                expand=["names"],
            )
            for issue_key in sorted(issues_by_key)
        ]
        log.info(
            f"Jira large-context fetch collected {len(detailed_issues)} unique issues "
            f"across {len(project_keys)} configured projects"
        )
        return ProviderFetchResult(
            records=[
                {
                    "cloud_id": cloud_id,
                    "site_name": metadata.get("site_name") or "Jira Site",
                    "site_url": metadata.get("site_url"),
                    "project_names_by_key": metadata.get("project_names_by_key") or {},
                    "issues": detailed_issues,
                    "project_keys": project_keys,
                }
            ],
            next_cursor={"since": datetime.now(timezone.utc).isoformat()},
            metadata={
                "backfill_since": since,
                "site_name": metadata.get("site_name"),
                "site_url": metadata.get("site_url"),
                "project_keys": project_keys,
            },
        )

    def build_snapshot(
        self,
        fetch_result: ProviderFetchResult,
        previous_snapshot: ProviderSnapshot | None = None,
    ) -> ProviderSnapshot:
        record = fetch_result.records[0] if fetch_result.records else {}
        cloud_id = record.get("cloud_id") or "jira:unknown"
        site_name = record.get("site_name") or "Jira"
        site_url = record.get("site_url")
        site_container_id = f"jira:site:{cloud_id}"
        containers = [
            SnapshotContainer(
                container_type="site",
                container_id=site_container_id,
                title=site_name,
                source_url=site_url,
            )
        ]
        people_map: Dict[str, SnapshotPerson] = {}
        entities: list[SnapshotEntity] = []
        cross_links: list[SnapshotCrossLink] = []
        open_questions: list[str] = []
        watch_items: list[str] = []
        project_names_by_key = record.get("project_names_by_key") or {}
        since_marker = fetch_result.metadata.get("backfill_since")

        for project_key in record.get("project_keys", []):
            containers.append(
                SnapshotContainer(
                    container_type="project",
                    container_id=f"jira:project:{project_key}",
                    parent_id=site_container_id,
                    title=project_names_by_key.get(project_key) or project_key,
                    source_url=f"{site_url.rstrip('/')}/projects/{project_key}" if site_url else None,
                )
            )

        for issue in record.get("issues", []):
            fields = issue.get("fields") or {}
            project = fields.get("project") or {}
            project_key = project.get("key") or "UNKNOWN"
            project_name = project.get("name") or project_names_by_key.get(project_key) or project_key
            issue_key = issue.get("key") or issue.get("id") or "UNKNOWN-0"
            issue_url = f"{site_url.rstrip('/')}/browse/{issue_key}" if site_url else None
            description_text = JiraClient.adf_to_text(fields.get("description")).strip()
            comment_entries = ((fields.get("comment") or {}).get("comments") or [])
            comment_texts = [JiraClient.adf_to_text(comment.get("body")).strip() for comment in comment_entries]
            issue_texts = [description_text, *comment_texts]
            refs = extract_external_references(issue_texts, current_jira_key=issue_key)
            related_entities = [
                *refs["github"],
                *refs["jira"],
                *refs["slack"],
                *refs["notion"],
            ]

            assignee = self._person_display(fields.get("assignee"))
            reporter = self._person_display(fields.get("reporter"))
            comment_authors = [
                self._person_display(comment.get("author"))
                for comment in comment_entries
                if self._person_display(comment.get("author"))
            ]
            people = [person for person in [assignee, reporter, *comment_authors] if person]
            self._upsert_people(
                people_map,
                [
                    fields.get("assignee"),
                    fields.get("reporter"),
                    *[comment.get("author") for comment in comment_entries],
                ],
                related_entity=f"jira:{issue_key}",
            )

            entity = SnapshotEntity(
                entity_type="ticket",
                external_id=f"jira:{issue_key}",
                title=fields.get("summary") or issue_key,
                status=((fields.get("status") or {}).get("name") or "open"),
                summary=(description_text or fields.get("summary") or issue_key)[:1200],
                project=project_key,
                feature_tags=[self._field_name(fields.get("priority")), self._field_name(fields.get("issuetype"))],
                people=people,
                related_entities=related_entities,
                updated_at=fields.get("updated"),
                source_url=issue_url,
                container_id=f"jira:project:{project_key}",
                extra_fields={
                    "ticket_key": issue_key,
                    "issue_type": self._field_name(fields.get("issuetype")),
                    "priority": self._field_name(fields.get("priority")),
                    "assignee": assignee,
                    "reporter": reporter,
                    "sprint": self._extract_sprint(issue),
                    "epic": self._extract_epic(issue),
                    "linked_github_ids": refs["github"],
                    "linked_slack_ids": refs["slack"],
                },
            )
            entities.append(entity)

            for target in related_entities:
                cross_links.append(
                    SnapshotCrossLink(
                        source_entity_id=f"jira:{issue_key}",
                        target_entity_id=target,
                        relationship="references",
                    )
                )

            if self._is_recent(fields.get("created"), since_marker):
                open_questions.append(f"New ticket {issue_key}: {fields.get('summary') or issue_key}")

            if self._is_done(fields) and self._is_recent(fields.get("updated"), since_marker):
                watch_items.append(f"Closed ticket {issue_key}: {fields.get('summary') or issue_key}")

            if not assignee and self._field_name(fields.get("priority")) in {"Highest", "High", "Blocker"} and not self._is_done(fields):
                watch_items.append(f"Unassigned high-priority ticket {issue_key} in {project_name}")

            if self._is_stale_in_progress(fields.get("status"), fields.get("updated")):
                watch_items.append(f"Stale in-progress ticket {issue_key} has not moved recently")

        deduped_watch_items = list(dict.fromkeys(item for item in watch_items if item))
        deduped_open_questions = list(dict.fromkeys(item for item in open_questions if item))

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
            open_questions=deduped_open_questions,
            watch_items=deduped_watch_items,
        )

    def _person_display(self, person: Any) -> str:
        if not isinstance(person, dict):
            return ""
        return person.get("displayName") or person.get("emailAddress") or person.get("accountId") or ""

    def _field_name(self, field: Any) -> str:
        if isinstance(field, dict):
            return field.get("name") or field.get("value") or ""
        return str(field or "")

    def _extract_sprint(self, issue: dict[str, Any]) -> str:
        names = issue.get("names") or {}
        fields = issue.get("fields") or {}
        for field_id, field_name in names.items():
            if "sprint" not in str(field_name).lower():
                continue
            value = fields.get(field_id)
            if isinstance(value, list) and value:
                sprint = value[-1]
                if isinstance(sprint, dict):
                    return sprint.get("name") or sprint.get("state") or ""
            if isinstance(value, dict):
                return value.get("name") or value.get("state") or ""
        return ""

    def _extract_epic(self, issue: dict[str, Any]) -> str:
        fields = issue.get("fields") or {}
        names = issue.get("names") or {}
        parent = fields.get("parent") or {}
        parent_key = parent.get("key")
        if parent_key:
            return parent_key
        for field_id, field_name in names.items():
            if "epic" not in str(field_name).lower():
                continue
            value = fields.get(field_id)
            if isinstance(value, dict):
                return value.get("key") or value.get("value") or value.get("name") or ""
            if isinstance(value, str):
                return value
        return ""

    def _upsert_people(self, people_map: Dict[str, SnapshotPerson], people: Iterable[Any], related_entity: str) -> None:
        for person in people:
            if not isinstance(person, dict):
                continue
            identifier = person.get("accountId") or person.get("emailAddress") or person.get("displayName")
            display_name = person.get("displayName") or person.get("emailAddress") or identifier
            if not identifier or not display_name:
                continue
            entry = people_map.get(identifier)
            if entry is None:
                entry = SnapshotPerson(
                    identifier=identifier,
                    display_name=display_name,
                    role="jira_user",
                    related_entities=[],
                )
                people_map[identifier] = entry
            if related_entity not in entry.related_entities:
                entry.related_entities.append(related_entity)

    def _format_jql_datetime(self, since_ts: str) -> str:
        dt = self._parse_datetime(since_ts) or datetime.now(timezone.utc) - timedelta(days=14)
        return dt.astimezone(timezone.utc).strftime("%Y/%m/%d %H:%M")

    def _parse_datetime(self, value: Optional[str]) -> Optional[datetime]:
        if not value:
            return None
        try:
            if value.endswith("Z"):
                value = value[:-1] + "+00:00"
            return datetime.fromisoformat(value)
        except ValueError:
            return None

    def _is_recent(self, value: Optional[str], since_marker: Optional[str]) -> bool:
        dt = self._parse_datetime(value)
        since = self._parse_datetime(since_marker)
        return bool(dt and since and dt >= since)

    def _is_done(self, fields: dict[str, Any]) -> bool:
        status = fields.get("status") or {}
        category = (status.get("statusCategory") or {}).get("name") or ""
        return category.lower() == "done" or self._field_name(status).lower() in {"done", "closed", "resolved"}

    def _is_stale_in_progress(self, status: Any, updated_at: Optional[str]) -> bool:
        status_name = self._field_name(status).lower()
        if "progress" not in status_name:
            return False
        updated = self._parse_datetime(updated_at)
        if not updated:
            return False
        if updated.tzinfo is None:
            updated = updated.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) - updated >= timedelta(days=7)
