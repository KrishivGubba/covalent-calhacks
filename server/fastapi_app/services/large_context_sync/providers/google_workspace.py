"""Google Workspace large-context provider."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from email.utils import getaddresses
from typing import Dict, Iterable, Optional

from covalent_mcp.toolclasses.google.calendar.calendar_client import CalendarService
from covalent_mcp.toolclasses.google.drive.drive_client import DriveService
from covalent_mcp.toolclasses.google.mail.gmail_client import GmailService

from ..models import (
    ProviderFetchResult,
    ProviderSnapshot,
    SnapshotContainer,
    SnapshotEntity,
    SnapshotPerson,
)
from .base import LargeContextProvider


class GoogleWorkspaceLargeContextProvider(LargeContextProvider):
    provider_id = "google_workspace"
    display_name = "Google Workspace"
    supports_live_sync = True
    file_name = "google_workspace.md"
    integration_provider_key = "google"

    def fetch_delta(self, cursor: Optional[dict], since_ts: str) -> ProviderFetchResult:
        gmail = GmailService()
        drive = DriveService()
        calendar = CalendarService()
        calendars = calendar.list_calendars()
        since = (cursor or {}).get("since") or since_ts
        time_min = since
        time_max = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
        return ProviderFetchResult(
            records=[
                {
                    "mailbox": gmail.list_messages(query="newer_than:14d", max_results=25),
                    "drive_root": drive.list_folder(folder_id="root", max_results=25),
                    "calendars": calendars,
                    "events_by_calendar": {
                        cal.get("id", "primary"): calendar.list_events(
                            calendar_id=cal.get("id", "primary"),
                            time_min=time_min,
                            time_max=time_max,
                            max_results=20,
                        )
                        for cal in calendars[:5]
                    },
                }
            ],
            next_cursor={"since": datetime.now(timezone.utc).isoformat()},
            metadata={"backfill_since": since},
        )

    def build_snapshot(self, fetch_result: ProviderFetchResult, previous_snapshot: ProviderSnapshot | None = None) -> ProviderSnapshot:
        people_map: Dict[str, SnapshotPerson] = {}
        containers = [
            SnapshotContainer(container_type="account", container_id="google:account", title="Primary Google Account"),
            SnapshotContainer(container_type="mailbox", container_id="gmail:mailbox", title="Gmail Inbox", parent_id="google:account"),
            SnapshotContainer(container_type="shared_drive", container_id="gdrive:root", title="Google Drive Root", parent_id="google:account"),
        ]
        entities: list[SnapshotEntity] = []

        record = fetch_result.records[0] if fetch_result.records else {}
        threads = defaultdict(list)
        for message in record.get("mailbox", []):
            threads[message.get("threadId") or message.get("id")].append(message)

        for thread_id, messages in threads.items():
            latest = max(messages, key=lambda message: message.get("date", ""))
            participants = self._extract_message_people(messages)
            entities.append(
                SnapshotEntity(
                    entity_type="email_thread",
                    external_id=f"gmail:{thread_id}",
                    title=latest.get("subject") or f"Email thread {thread_id}",
                    status="active",
                    summary=latest.get("snippet") or latest.get("subject") or "",
                    project="gmail",
                    feature_tags=latest.get("labelIds", []),
                    people=participants,
                    related_entities=[],
                    updated_at=latest.get("date"),
                    source_url=None,
                    container_id="gmail:mailbox",
                    extra_fields={
                        "thread_id": thread_id,
                        "subject": latest.get("subject") or "",
                        "participants": participants,
                        "last_message_at": latest.get("date"),
                        "labels": latest.get("labelIds", []),
                        "linked_entities": [],
                    },
                )
            )
            self._upsert_people(people_map, participants, f"gmail:{thread_id}", role="email_participant")

        for file in record.get("drive_root", {}).get("files", []):
            mime_type = file.get("mimeType") or ""
            entity_type = "doc" if mime_type.startswith("application/vnd.google-apps.") and mime_type != "application/vnd.google-apps.folder" else "drive_file"
            external_id = f"gdrive:{file.get('id')}"
            entities.append(
                SnapshotEntity(
                    entity_type=entity_type,
                    external_id=external_id,
                    title=file.get("name") or file.get("id") or "Drive file",
                    status="active",
                    summary=f"Drive file in root: {file.get('name')}",
                    project="drive",
                    feature_tags=[],
                    people=[],
                    related_entities=[],
                    updated_at=file.get("modifiedTime"),
                    source_url=file.get("webViewLink"),
                    container_id="gdrive:root",
                    extra_fields={
                        "file_id": file.get("id"),
                        "mime_type": mime_type,
                        "owner": "",
                        "folder_path": "/",
                        "last_modified_by": "",
                        "doc_type": mime_type if entity_type == "doc" else "",
                    },
                )
            )

        for calendar in record.get("calendars", [])[:5]:
            container_id = f"calendar:{calendar.get('id')}"
            containers.append(
                SnapshotContainer(
                    container_type="calendar",
                    container_id=container_id,
                    title=calendar.get("summary") or calendar.get("id") or "Calendar",
                    parent_id="google:account",
                )
            )
            for event in record.get("events_by_calendar", {}).get(calendar.get("id"), []):
                attendees = [attendee.get("email") for attendee in event.get("attendees") or [] if attendee.get("email")]
                external_id = f"calendar:{event.get('id')}"
                entities.append(
                    SnapshotEntity(
                        entity_type="calendar_event",
                        external_id=external_id,
                        title=event.get("summary") or "Calendar event",
                        status=event.get("status") or "confirmed",
                        summary=event.get("description") or event.get("summary") or "",
                        project=calendar.get("summary") or "calendar",
                        feature_tags=[],
                        people=attendees,
                        related_entities=[],
                        updated_at=(event.get("start") or {}).get("dateTime") or (event.get("start") or {}).get("date"),
                        source_url=event.get("hangoutLink"),
                        container_id=container_id,
                        extra_fields={
                            "event_id": event.get("id"),
                            "start_at": (event.get("start") or {}).get("dateTime") or (event.get("start") or {}).get("date"),
                            "end_at": (event.get("end") or {}).get("dateTime") or (event.get("end") or {}).get("date"),
                            "attendees": attendees,
                            "meeting_project": calendar.get("summary") or "",
                        },
                    )
                )
                self._upsert_people(people_map, attendees, external_id, role="meeting_attendee")

        return ProviderSnapshot(
            provider_id=self.provider_id,
            provider_display_name=self.display_name,
            generated_at=datetime.now(timezone.utc).isoformat(),
            cursor=fetch_result.next_cursor,
            metadata=fetch_result.metadata,
            containers=containers,
            entities=entities,
            relevant_people=sorted(people_map.values(), key=lambda person: person.display_name.lower()),
        )

    def _extract_message_people(self, messages: Iterable[dict]) -> list[str]:
        participants: list[str] = []
        for message in messages:
            raw_addresses = [message.get("from", ""), message.get("to", "")]
            for _, email in getaddresses(raw_addresses):
                if email and email not in participants:
                    participants.append(email)
        return participants

    def _upsert_people(self, people_map: Dict[str, SnapshotPerson], identifiers: Iterable[str], related_entity: str, *, role: str) -> None:
        for identifier in identifiers:
            if not identifier:
                continue
            person = people_map.get(identifier)
            if person is None:
                person = SnapshotPerson(identifier=identifier, display_name=identifier, role=role, related_entities=[])
                people_map[identifier] = person
            if related_entity not in person.related_entities:
                person.related_entities.append(related_entity)
