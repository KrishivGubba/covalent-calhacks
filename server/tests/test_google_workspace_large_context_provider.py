from __future__ import annotations

import sys
from email.utils import format_datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.append(str(ROOT / "context-engine"))

from server.fastapi_app.services.large_context_sync.providers.google_workspace import (  # noqa: E402
    GoogleWorkspaceLargeContextProvider,
)


class FakeIntegrationDAO:
    def __init__(self, token_data: dict[str, Any]):
        self._token_data = token_data

    def get_token(self, provider: str):
        if provider != "google":
            return None
        return self._token_data


def test_google_workspace_provider_builds_entities_links_and_heuristics(monkeypatch):
    import server.fastapi_app.services.large_context_sync.providers.google_workspace as google_workspace

    now = google_workspace.datetime.now(google_workspace.timezone.utc)
    since_marker = (now - google_workspace.timedelta(hours=6)).isoformat()

    latest_thread_dt = now - google_workspace.timedelta(hours=1)
    old_thread_dt = now - google_workspace.timedelta(hours=72)
    bootstrap_thread_dt = now - google_workspace.timedelta(days=20)
    drive_modified_dt = now - google_workspace.timedelta(hours=2)
    meeting_without_links = now + google_workspace.timedelta(days=3)
    meeting_with_links = now + google_workspace.timedelta(hours=20)

    class FakeGmailService:
        queries: list[str] = []

        def list_messages(self, query=None, max_results=10, label_ids=None):  # noqa: ARG002
            self.__class__.queries.append(query or "")
            if query and query.startswith("after:"):
                return [
                    {
                        "id": "msg-thread-1-old",
                        "threadId": "thread-1",
                        "snippet": "Older snippet",
                        "from": "Teammate <teammate@acme.com>",
                        "to": "User <user@acme.com>",
                        "cc": "",
                        "subject": "Older thread subject",
                        "date": format_datetime(latest_thread_dt - google_workspace.timedelta(minutes=10)),
                        "internalDate": str(
                            int((latest_thread_dt - google_workspace.timedelta(minutes=10)).timestamp() * 1000)
                        ),
                        "labelIds": ["INBOX"],
                    },
                    {
                        "id": "msg-thread-1-new",
                        "threadId": "thread-1",
                        "snippet": "Latest snippet",
                        "from": "Vendor <vendor@example.com>",
                        "to": "User <user@acme.com>",
                        "cc": "Lead <lead@acme.com>",
                        "subject": "Review github.com/acme/api#42",
                        "date": format_datetime(latest_thread_dt),
                        "internalDate": str(int(latest_thread_dt.timestamp() * 1000)),
                        "labelIds": ["INBOX", "UNREAD"],
                    },
                    {
                        "id": "msg-thread-2",
                        "threadId": "thread-2",
                        "snippet": "Please reply",
                        "from": "Partner <partner@example.com>",
                        "to": "User <user@acme.com>",
                        "cc": "",
                        "subject": "Need response",
                        "date": format_datetime(old_thread_dt),
                        "internalDate": str(int(old_thread_dt.timestamp() * 1000)),
                        "labelIds": ["INBOX", "UNREAD", "IMPORTANT", "STARRED"],
                    },
                ]
            if query == "newer_than:90d":
                return [
                    {
                        "id": "msg-bootstrap",
                        "threadId": "thread-3",
                        "snippet": "Bootstrap thread",
                        "from": "Archive <archive@example.com>",
                        "to": "User <user@acme.com>",
                        "cc": "",
                        "subject": "Bootstrap history",
                        "date": format_datetime(bootstrap_thread_dt),
                        "internalDate": str(int(bootstrap_thread_dt.timestamp() * 1000)),
                        "labelIds": ["INBOX"],
                    }
                ]
            raise AssertionError(f"Unexpected Gmail query: {query}")

        def get_message(self, message_id: str):
            bodies = {
                "msg-thread-1-new": {
                    "body": "Please check PROJ-10 and https://acme.slack.com/archives/C123/p1713456000000000",
                },
                "msg-thread-2": {
                    "body": "Escalating this request.",
                },
                "msg-bootstrap": {
                    "body": "Historical context only.",
                },
            }
            return {
                "id": message_id,
                "threadId": "thread-1" if "thread-1" in message_id else "thread-2" if message_id == "msg-thread-2" else "thread-3",
                "snippet": bodies.get(message_id, {}).get("body", ""),
                "from": "sender@example.com",
                "to": "user@acme.com",
                "cc": "",
                "subject": "Expanded message",
                "date": format_datetime(now),
                "internalDate": str(int(now.timestamp() * 1000)),
                "body": bodies.get(message_id, {}).get("body", ""),
                "labelIds": [],
            }

    class FakeDriveService:
        queries: list[str] = []

        def search_files(self, query: str, max_results=50, page_token=None, order_by="modifiedTime desc"):  # noqa: ARG002
            self.__class__.queries.append(query)
            if "mimeType = 'application/vnd.google-apps.document'" in query:
                return {
                    "files": [
                        {
                            "id": "doc-1",
                            "name": "Roadmap",
                            "mimeType": "application/vnd.google-apps.document",
                            "modifiedTime": drive_modified_dt.isoformat(),
                            "webViewLink": "https://docs.google.com/document/d/doc-1/edit",
                            "parents": ["folder-product"],
                            "owners": [{"displayName": "Doc Owner", "emailAddress": "owner@acme.com"}],
                            "lastModifyingUser": {"displayName": "Doc Editor", "emailAddress": "editor@acme.com"},
                        }
                    ]
                }
            if "mimeType = 'text/markdown'" in query or "mimeType = 'text/plain'" in query:
                return {"files": []}
            return {
                "files": [
                    {
                        "id": "file-2",
                        "name": "notes.txt",
                        "mimeType": "text/plain",
                        "modifiedTime": (drive_modified_dt - google_workspace.timedelta(minutes=30)).isoformat(),
                        "webViewLink": "https://drive.google.com/file/d/file-2/view",
                        "parents": ["root"],
                        "owners": [{"displayName": "Ops Owner", "emailAddress": "ops@acme.com"}],
                        "lastModifyingUser": {"displayName": "Ops Owner", "emailAddress": "ops@acme.com"},
                    }
                ]
            }

        def get_file(self, file_id: str):
            if file_id == "doc-1":
                return {
                    "id": "doc-1",
                    "name": "Roadmap",
                    "mimeType": "application/vnd.google-apps.document",
                    "modifiedTime": drive_modified_dt.isoformat(),
                    "webViewLink": "https://docs.google.com/document/d/doc-1/edit",
                    "parents": ["folder-product"],
                    "owners": [{"displayName": "Doc Owner", "emailAddress": "owner@acme.com"}],
                    "lastModifyingUser": {"displayName": "Doc Editor", "emailAddress": "editor@acme.com"},
                }
            if file_id == "file-2":
                return {
                    "id": "file-2",
                    "name": "notes.txt",
                    "mimeType": "text/plain",
                    "modifiedTime": (drive_modified_dt - google_workspace.timedelta(minutes=30)).isoformat(),
                    "webViewLink": "https://drive.google.com/file/d/file-2/view",
                    "parents": ["root"],
                    "owners": [{"displayName": "Ops Owner", "emailAddress": "ops@acme.com"}],
                    "lastModifyingUser": {"displayName": "Ops Owner", "emailAddress": "ops@acme.com"},
                }
            if file_id == "folder-product":
                return {
                    "id": "folder-product",
                    "name": "Product",
                    "mimeType": "application/vnd.google-apps.folder",
                    "webViewLink": "https://drive.google.com/drive/folders/folder-product",
                    "parents": ["folder-team"],
                }
            if file_id == "folder-team":
                return {
                    "id": "folder-team",
                    "name": "Team",
                    "mimeType": "application/vnd.google-apps.folder",
                    "webViewLink": "https://drive.google.com/drive/folders/folder-team",
                    "parents": ["root"],
                }
            return None

        def get_file_content(self, file_id: str):
            if file_id == "doc-1":
                return "Launch plan references PROJ-9 and https://acme.slack.com/archives/C777/p1713456000000000"
            if file_id == "file-2":
                return "General notes"
            return None

        def resolve_path(self, parents=None, cache=None):
            cache = cache if cache is not None else {}
            if not parents or parents[0] == "root":
                return "/"
            current = parents[0]
            parts: list[str] = []
            while current and current != "root":
                if current not in cache:
                    cache[current] = self.get_file(current)
                folder = cache[current]
                parts.append(folder["name"])
                parent_ids = folder.get("parents") or []
                current = parent_ids[0] if parent_ids else "root"
            return "/" + "/".join(reversed(parts))

    class FakeCalendarService:
        def list_calendars(self):
            return [
                {"id": "primary", "summary": "Primary", "primary": True},
                {"id": "eng", "summary": "Engineering", "primary": False},
            ]

        def list_events(self, time_min=None, time_max=None, max_results=250, show_deleted=False, calendar_id="primary", updated_min=None):  # noqa: ARG002
            if calendar_id == "primary":
                return [
                    {
                        "id": "event-no-links",
                        "summary": "Roadmap review",
                        "description": "Quarterly planning",
                        "start": {"dateTime": meeting_without_links.isoformat()},
                        "end": {"dateTime": (meeting_without_links + google_workspace.timedelta(hours=1)).isoformat()},
                        "updated": now.isoformat(),
                        "status": "confirmed",
                        "creator": {"email": "organizer@acme.com"},
                        "organizer": {"email": "organizer@acme.com"},
                        "attendees": [
                            {"email": "a@acme.com"},
                            {"email": "b@acme.com"},
                            {"email": "c@acme.com"},
                            {"email": "d@acme.com"},
                        ],
                        "location": "HQ",
                        "htmlLink": "https://calendar.google.com/event?eid=no-links",
                        "hangoutLink": "https://meet.google.com/no-links",
                    },
                    {
                        "id": "event-linked",
                        "summary": "Launch checkpoint",
                        "description": "Review github.com/acme/api#77 before tomorrow",
                        "start": {"dateTime": meeting_with_links.isoformat()},
                        "end": {"dateTime": (meeting_with_links + google_workspace.timedelta(hours=1)).isoformat()},
                        "updated": now.isoformat(),
                        "status": "confirmed",
                        "creator": {"email": "pm@acme.com"},
                        "organizer": {"email": "pm@acme.com"},
                        "attendees": [
                            {"email": "pm@acme.com"},
                            {"email": "eng@acme.com"},
                        ],
                        "location": "Zoom",
                        "htmlLink": "https://calendar.google.com/event?eid=linked",
                        "hangoutLink": "https://meet.google.com/linked",
                    },
                ]
            return []

    monkeypatch.setattr(google_workspace, "GmailService", FakeGmailService)
    monkeypatch.setattr(google_workspace, "DriveService", FakeDriveService)
    monkeypatch.setattr(google_workspace, "CalendarService", FakeCalendarService)

    provider = GoogleWorkspaceLargeContextProvider(
        FakeIntegrationDAO({"access_token": "google-access", "provider_metadata": {"email": "user@acme.com"}})
    )

    fetch_result = provider.fetch_delta(None, since_marker)
    assert fetch_result.next_cursor["bootstrap_remaining"] == 2
    assert fetch_result.next_cursor["gmail_after_ts"]
    assert fetch_result.next_cursor["drive_after_ts"]
    assert fetch_result.next_cursor["calendar_after_ts"]
    assert "newer_than:90d" in FakeGmailService.queries
    assert any(query.startswith("after:") for query in FakeGmailService.queries)
    assert any("mimeType = 'application/vnd.google-apps.document'" in query for query in FakeDriveService.queries)

    snapshot = provider.build_snapshot(fetch_result)

    entity_ids = {entity.external_id for entity in snapshot.entities}
    assert "gmail:thread-1" in entity_ids
    assert "gdrive:doc-1" in entity_ids
    assert "calendar:primary:event-linked" in entity_ids
    assert any(container.container_id == "gdrive:folder:folder-product" for container in snapshot.containers)

    email_entity = next(entity for entity in snapshot.entities if entity.external_id == "gmail:thread-1")
    assert email_entity.title == "Review github.com/acme/api#42"
    assert "github:acme/api#42" in email_entity.related_entities
    assert "jira:PROJ-10" in email_entity.related_entities

    drive_entity = next(entity for entity in snapshot.entities if entity.external_id == "gdrive:doc-1")
    assert drive_entity.entity_type == "doc"
    assert drive_entity.container_id == "gdrive:folder:folder-product"
    assert drive_entity.project == "Team"
    assert "jira:PROJ-9" in drive_entity.related_entities

    assert any(link.target_entity_id == "slack:C777:1713456000.000000" for link in snapshot.cross_links)
    assert any("Unread external thread" in item for item in snapshot.open_questions)
    assert any("Upcoming meeting lacks linked work artifacts" in item for item in snapshot.open_questions)
    assert any("Important unread email thread is aging" in item for item in snapshot.watch_items)
    assert any("Updated Drive artifact links to active work" in item for item in snapshot.watch_items)
    assert any("Upcoming meeting already references active work" in item for item in snapshot.watch_items)
    assert {"Doc Owner", "Doc Editor", "vendor@example.com", "pm@acme.com"} <= {
        person.display_name for person in snapshot.relevant_people
    }


def test_google_workspace_provider_bootstrap_counts_down(monkeypatch):
    import server.fastapi_app.services.large_context_sync.providers.google_workspace as google_workspace

    class FakeGmailService:
        queries: list[str] = []

        def list_messages(self, query=None, max_results=10, label_ids=None):  # noqa: ARG002
            self.__class__.queries.append(query or "")
            return []

        def get_message(self, message_id: str):  # noqa: ARG002
            return None

    class FakeDriveService:
        def search_files(self, query: str, max_results=50, page_token=None, order_by="modifiedTime desc"):  # noqa: ARG002
            return {"files": []}

        def get_file(self, file_id: str):  # noqa: ARG002
            return None

        def get_file_content(self, file_id: str):  # noqa: ARG002
            return None

        def resolve_path(self, parents=None, cache=None):  # noqa: ARG002
            return "/"

    class FakeCalendarService:
        def list_calendars(self):
            return []

        def list_events(self, time_min=None, time_max=None, max_results=250, show_deleted=False, calendar_id="primary", updated_min=None):  # noqa: ARG002
            return []

    monkeypatch.setattr(google_workspace, "GmailService", FakeGmailService)
    monkeypatch.setattr(google_workspace, "DriveService", FakeDriveService)
    monkeypatch.setattr(google_workspace, "CalendarService", FakeCalendarService)

    provider = GoogleWorkspaceLargeContextProvider(
        FakeIntegrationDAO({"access_token": "google-access", "provider_metadata": {"email": "user@acme.com"}})
    )

    fetch_result = provider.fetch_delta(
        {"since": "2026-04-18T00:00:00+00:00", "bootstrap_remaining": 0},
        "2026-04-17T00:00:00+00:00",
    )
    assert fetch_result.next_cursor["bootstrap_remaining"] == 0
    assert len(FakeGmailService.queries) == 1
    assert FakeGmailService.queries[0].startswith("after:")
