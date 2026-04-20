from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.append(str(ROOT / "context-engine"))

from server.fastapi_app.services.large_context_sync.models import ProviderFetchResult
from server.fastapi_app.services.large_context_sync.providers.jira import JiraLargeContextProvider


class FakeIntegrationDAO:
    def __init__(self, token_data):
        self._token_data = token_data

    def get_token(self, provider: str):
        if provider != "jira":
            return None
        return self._token_data


def test_jira_provider_requires_site_and_project_allowlist():
    provider = JiraLargeContextProvider(FakeIntegrationDAO({"provider_metadata": {"cloud_id": "cloud-1", "project_keys": []}}))
    assert provider.is_connected(provider.integration_dao) is False

    configured_provider = JiraLargeContextProvider(
        FakeIntegrationDAO({"provider_metadata": {"cloud_id": "cloud-1", "project_keys": ["PROJ"]}})
    )
    assert configured_provider.is_connected(configured_provider.integration_dao) is True


def test_jira_snapshot_builds_entities_cross_links_and_watch_items():
    provider = JiraLargeContextProvider(FakeIntegrationDAO({"provider_metadata": {"cloud_id": "cloud-1", "project_keys": ["PROJ"]}}))
    fetch_result = ProviderFetchResult(
        records=[
            {
                "cloud_id": "cloud-1",
                "site_name": "Acme Jira",
                "site_url": "https://acme.atlassian.net",
                "project_keys": ["PROJ"],
                "project_names_by_key": {"PROJ": "Project Atlas"},
                "issues": [
                    {
                        "key": "PROJ-12",
                        "names": {"customfield_10010": "Sprint", "customfield_10011": "Epic Link"},
                        "fields": {
                            "summary": "Investigate rollout issue",
                            "description": {
                                "type": "doc",
                                "content": [
                                    {
                                        "type": "paragraph",
                                        "content": [
                                            {"type": "text", "text": "See github.com/acme/api#42 and PROJ-10"},
                                        ],
                                    }
                                ],
                            },
                            "status": {"name": "In Progress", "statusCategory": {"name": "In Progress"}},
                            "assignee": None,
                            "reporter": {"accountId": "acct-1", "displayName": "Reporter One"},
                            "priority": {"name": "High"},
                            "issuetype": {"name": "Bug"},
                            "project": {"key": "PROJ", "name": "Project Atlas"},
                            "updated": "2026-04-18T12:00:00+00:00",
                            "created": "2026-04-18T11:30:00+00:00",
                            "comment": {
                                "comments": [
                                    {
                                        "author": {"accountId": "acct-2", "displayName": "Commenter Two"},
                                        "body": {
                                            "type": "doc",
                                            "content": [
                                                {
                                                    "type": "paragraph",
                                                    "content": [
                                                        {
                                                            "type": "text",
                                                            "text": "Related Slack thread https://acme.slack.com/archives/C123/p1713456000000000",
                                                        }
                                                    ],
                                                }
                                            ],
                                        },
                                    }
                                ]
                            },
                            "customfield_10010": [{"name": "Sprint 42"}],
                            "customfield_10011": "PROJ-1",
                        },
                    }
                ],
            }
        ],
        next_cursor={"since": "2026-04-18T12:30:00+00:00"},
        metadata={"backfill_since": "2026-04-18T10:00:00+00:00"},
    )

    snapshot = provider.build_snapshot(fetch_result)
    assert snapshot.provider_id == "jira"
    assert any(container.container_type == "site" for container in snapshot.containers)
    assert any(container.container_type == "project" for container in snapshot.containers)
    assert len(snapshot.entities) == 1
    entity = snapshot.entities[0]
    assert entity.external_id == "jira:PROJ-12"
    assert entity.extra_fields["ticket_key"] == "PROJ-12"
    assert entity.extra_fields["sprint"] == "Sprint 42"
    assert entity.extra_fields["epic"] == "PROJ-1"
    assert entity.extra_fields["linked_slack_ids"] == ["slack:C123:1713456000.000000"]
    assert "github:acme/api#42" in entity.related_entities
    assert any(link.target_entity_id == "jira:PROJ-10" for link in snapshot.cross_links)
    assert any("New ticket PROJ-12" in item for item in snapshot.open_questions)
    assert any("Unassigned high-priority ticket PROJ-12" in item for item in snapshot.watch_items)
    assert {person.display_name for person in snapshot.relevant_people} == {"Commenter Two", "Reporter One"}
