"""Google Workspace large-context provider."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from email.utils import getaddresses, parsedate_to_datetime
from typing import Any, Dict, Iterable, Optional

from covalent_mcp.toolclasses.google.calendar.calendar_client import CalendarService
from covalent_mcp.toolclasses.google.drive.drive_client import DriveService
from covalent_mcp.toolclasses.google.mail.gmail_client import GmailService
from covalent_mcp.toolclasses.issue_tracker.common import extract_external_references
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


class GoogleWorkspaceLargeContextProvider(LargeContextProvider):
    provider_id = "google_workspace"
    display_name = "Google Workspace"
    supports_live_sync = True
    file_name = "google_workspace.md"
    integration_provider_key = "google"

    ACTIVE_GMAIL_DAYS = 14
    ACTIVE_GMAIL_MAX = 100
    BOOTSTRAP_GMAIL_DAYS = 90
    BOOTSTRAP_GMAIL_MAX = 250
    ACTIVE_DRIVE_DAYS = 14
    ACTIVE_DRIVE_MAX = 100
    BOOTSTRAP_DRIVE_DAYS = 90
    BOOTSTRAP_DRIVE_MAX = 220
    ACTIVE_CALENDAR_PAST_DAYS = 7
    ACTIVE_CALENDAR_FUTURE_DAYS = 30
    ACTIVE_CALENDAR_MAX = 30
    BOOTSTRAP_CALENDAR_PAST_DAYS = 30
    BOOTSTRAP_CALENDAR_FUTURE_DAYS = 60
    BOOTSTRAP_CALENDAR_MAX = 60
    MAX_CALENDARS = 8
    MAX_DRIVE_CONTENT_CHARS = 6000
    MAX_EMAIL_BODY_CHARS = 6000
    GOOGLE_DOC_MIME = "application/vnd.google-apps.document"
    GOOGLE_FOLDER_MIME = "application/vnd.google-apps.folder"
    TEXT_LIKE_MIME_TYPES = {
        "text/plain",
        "text/markdown",
        "text/csv",
        "application/json",
        "application/xml",
    }

    def __init__(self, integration_dao: IntegrationDAO):
        self.integration_dao = integration_dao

    def is_connected(self, integration_dao) -> bool:
        token = integration_dao.get_token("google")
        return bool(token and token.get("access_token"))

    def fetch_delta(self, cursor: Optional[dict], since_ts: str) -> ProviderFetchResult:
        token = self.integration_dao.get_token("google")
        if not token or not token.get("access_token"):
            raise RuntimeError("Google integration is not connected")

        metadata = token.get("provider_metadata") or {}
        gmail = GmailService()
        drive = DriveService()
        calendar = CalendarService()
        since = (cursor or {}).get("since") or since_ts
        include_bootstrap, next_bootstrap_remaining = self._bootstrap_state(cursor)
        now = datetime.now(timezone.utc)
        folder_cache: dict[str, dict[str, Any]] = {}
        account_email = metadata.get("email")

        mailbox = self._fetch_mailbox_threads(
            gmail,
            include_bootstrap=include_bootstrap,
        )
        drive_files = self._fetch_drive_files(
            drive,
            now=now,
            include_bootstrap=include_bootstrap,
            folder_cache=folder_cache,
        )
        calendars = self._select_calendars(calendar.list_calendars())
        events_by_calendar = self._fetch_calendar_events(
            calendar,
            calendars,
            now=now,
            include_bootstrap=include_bootstrap,
        )
        return ProviderFetchResult(
            records=[
                {
                    "account_email": account_email,
                    "mailbox": mailbox,
                    "drive_files": drive_files,
                    "drive_folders": list(folder_cache.values()),
                    "calendars": calendars,
                    "events_by_calendar": events_by_calendar,
                }
            ],
            next_cursor={
                "since": now.isoformat(),
                "bootstrap_remaining": next_bootstrap_remaining,
            },
            metadata={
                "backfill_since": since,
                "account_email": account_email,
                "bootstrap_included": include_bootstrap,
            },
        )

    def build_snapshot(
        self,
        fetch_result: ProviderFetchResult,
        previous_snapshot: ProviderSnapshot | None = None,
    ) -> ProviderSnapshot:
        record = fetch_result.records[0] if fetch_result.records else {}
        account_email = record.get("account_email") or fetch_result.metadata.get("account_email")
        account_container_id = f"google:account:{account_email or 'me'}"
        people_map: Dict[str, SnapshotPerson] = {}
        containers_by_id: dict[str, SnapshotContainer] = {
            account_container_id: SnapshotContainer(
                container_type="account",
                container_id=account_container_id,
                title=account_email or "Primary Google Account",
            ),
            "gmail:mailbox": SnapshotContainer(
                container_type="mailbox",
                container_id="gmail:mailbox",
                title="Gmail Inbox",
                parent_id=account_container_id,
            ),
            "gdrive:root": SnapshotContainer(
                container_type="shared_drive",
                container_id="gdrive:root",
                title="Google Drive Root",
                parent_id=account_container_id,
            ),
        }
        entities: list[SnapshotEntity] = []
        cross_links: list[SnapshotCrossLink] = []
        open_questions: list[str] = []
        watch_items: list[str] = []
        since_marker = fetch_result.metadata.get("backfill_since")

        drive_folders = {
            folder.get("id"): folder
            for folder in record.get("drive_folders", [])
            if folder.get("id")
        }

        for thread in record.get("mailbox", []):
            thread_id = thread.get("thread_id") or "unknown-thread"
            latest = thread.get("latest_message") or {}
            participants = self._extract_message_people(thread.get("messages") or [])
            latest_texts = [
                latest.get("subject") or "",
                latest.get("snippet") or "",
                latest.get("body") or "",
            ]
            refs = extract_external_references(latest_texts)
            related_entities = [
                *refs["github"],
                *refs["jira"],
                *refs["slack"],
                *refs["notion"],
            ]
            updated_at = self._message_updated_at(latest)
            unread = thread.get("unread") is True
            important = thread.get("important") is True
            starred = thread.get("starred") is True
            external = self._is_external_thread(participants, account_email)
            status = "unread" if unread else "active"
            entities.append(
                SnapshotEntity(
                    entity_type="email_thread",
                    external_id=f"gmail:{thread_id}",
                    title=latest.get("subject") or f"Email thread {thread_id}",
                    status=status,
                    summary=(latest.get("snippet") or latest.get("body") or latest.get("subject") or "")[:1200],
                    project="gmail",
                    feature_tags=latest.get("labelIds", []),
                    people=participants,
                    related_entities=related_entities,
                    updated_at=updated_at,
                    source_url=f"https://mail.google.com/mail/u/0/#inbox/{thread_id}",
                    container_id="gmail:mailbox",
                    extra_fields={
                        "thread_id": thread_id,
                        "subject": latest.get("subject") or "",
                        "participants": participants,
                        "last_message_at": updated_at,
                        "labels": latest.get("labelIds", []),
                        "linked_entities": related_entities,
                    },
                )
            )
            self._upsert_identifier_people(
                people_map,
                participants,
                related_entity=f"gmail:{thread_id}",
                role="email_participant",
            )
            for target in related_entities:
                cross_links.append(
                    SnapshotCrossLink(
                        source_entity_id=f"gmail:{thread_id}",
                        target_entity_id=target,
                        relationship="references",
                    )
                )
            if unread and external and self._is_recent(updated_at, since_marker):
                open_questions.append(f"Unread external thread: {latest.get('subject') or thread_id}")
            if unread and (important or starred) and self._is_older_than(updated_at, hours=48):
                watch_items.append(f"Important unread email thread is aging: {latest.get('subject') or thread_id}")

        for folder_id, folder in drive_folders.items():
            self._ensure_drive_folder_container(folder_id, drive_folders, containers_by_id)

        for file in record.get("drive_files", []):
            mime_type = file.get("mimeType") or ""
            entity_type = "doc" if mime_type == self.GOOGLE_DOC_MIME else "drive_file"
            external_id = f"gdrive:{file.get('id')}"
            refs = extract_external_references([file.get("name") or "", file.get("content_excerpt") or ""])
            related_entities = [
                *refs["github"],
                *refs["jira"],
                *refs["slack"],
                *refs["notion"],
            ]
            owner_people = file.get("owners") or []
            last_modifier = file.get("lastModifyingUser")
            people = self._people_from_google_people(owner_people)
            if isinstance(last_modifier, dict):
                last_modifier_display = self._google_person_display(last_modifier)
                if last_modifier_display and last_modifier_display not in people:
                    people.append(last_modifier_display)

            parent_container_id = self._resolve_drive_container_id(file.get("parents"), drive_folders)
            project = self._drive_project(file.get("folder_path") or "/", entity_type)
            summary_text = file.get("content_excerpt") or file.get("name") or "Drive file"
            entities.append(
                SnapshotEntity(
                    entity_type=entity_type,
                    external_id=external_id,
                    title=file.get("name") or file.get("id") or "Drive file",
                    status="active",
                    summary=summary_text[:1200],
                    project=project,
                    feature_tags=[],
                    people=people,
                    related_entities=related_entities,
                    updated_at=file.get("modifiedTime"),
                    source_url=file.get("webViewLink"),
                    container_id=parent_container_id,
                    extra_fields={
                        "file_id": file.get("id"),
                        "mime_type": mime_type,
                        "owner": self._google_person_display(owner_people[0]) if owner_people else "",
                        "folder_path": file.get("folder_path") or "/",
                        "last_modified_by": self._google_person_display(last_modifier) if isinstance(last_modifier, dict) else "",
                        "doc_type": mime_type if entity_type == "doc" else "",
                    },
                )
            )
            self._upsert_google_people(
                people_map,
                owner_people,
                related_entity=external_id,
                role="drive_collaborator",
            )
            if isinstance(last_modifier, dict):
                self._upsert_google_people(
                    people_map,
                    [last_modifier],
                    related_entity=external_id,
                    role="drive_collaborator",
                )
            for target in related_entities:
                cross_links.append(
                    SnapshotCrossLink(
                        source_entity_id=external_id,
                        target_entity_id=target,
                        relationship="references",
                    )
                )
            if related_entities and self._is_recent(file.get("modifiedTime"), since_marker):
                watch_items.append(f"Updated Drive artifact links to active work: {file.get('name') or file.get('id')}")

        for calendar in record.get("calendars", []):
            container_id = f"calendar:{calendar.get('id')}"
            containers_by_id[container_id] = SnapshotContainer(
                container_type="calendar",
                container_id=container_id,
                title=calendar.get("summary") or calendar.get("id") or "Calendar",
                parent_id=account_container_id,
            )
            for event in record.get("events_by_calendar", {}).get(calendar.get("id"), []):
                attendees = self._calendar_people(event)
                refs = extract_external_references([
                    event.get("summary") or "",
                    event.get("description") or "",
                    event.get("location") or "",
                ])
                related_entities = [
                    *refs["github"],
                    *refs["jira"],
                    *refs["slack"],
                    *refs["notion"],
                ]
                external_id = f"calendar:{calendar.get('id')}:{event.get('id')}"
                updated_at = event.get("updated")
                entities.append(
                    SnapshotEntity(
                        entity_type="calendar_event",
                        external_id=external_id,
                        title=event.get("summary") or "Calendar event",
                        status=event.get("status") or "confirmed",
                        summary=event.get("description") or event.get("summary") or "",
                        project=calendar.get("summary") or "calendar",
                        feature_tags=["recurring"] if event.get("recurringEventId") else [],
                        people=attendees,
                        related_entities=related_entities,
                        updated_at=updated_at,
                        source_url=event.get("htmlLink") or event.get("hangoutLink"),
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
                self._upsert_google_people(
                    people_map,
                    self._calendar_people_dicts(event),
                    related_entity=external_id,
                    role="meeting_attendee",
                )
                for target in related_entities:
                    cross_links.append(
                        SnapshotCrossLink(
                            source_entity_id=external_id,
                            target_entity_id=target,
                            relationship="references",
                        )
                    )
                if self._is_upcoming(event, within_days=7) and len(attendees) >= 4 and not related_entities:
                    open_questions.append(
                        f"Upcoming meeting lacks linked work artifacts: {event.get('summary') or event.get('id')}"
                    )
                if self._is_upcoming(event, within_hours=24) and related_entities:
                    watch_items.append(
                        f"Upcoming meeting already references active work: {event.get('summary') or event.get('id')}"
                    )

        return ProviderSnapshot(
            provider_id=self.provider_id,
            provider_display_name=self.display_name,
            generated_at=datetime.now(timezone.utc).isoformat(),
            cursor=fetch_result.next_cursor,
            metadata=fetch_result.metadata,
            containers=list(containers_by_id.values()),
            entities=entities,
            relevant_people=sorted(people_map.values(), key=lambda person: person.display_name.lower()),
            cross_links=cross_links,
            open_questions=list(dict.fromkeys(item for item in open_questions if item)),
            watch_items=list(dict.fromkeys(item for item in watch_items if item)),
        )

    def _bootstrap_state(self, cursor: Optional[dict]) -> tuple[bool, int]:
        if not cursor or "bootstrap_remaining" not in cursor:
            return True, 2
        try:
            remaining = max(int(cursor.get("bootstrap_remaining") or 0), 0)
        except (TypeError, ValueError):
            return True, 2
        return remaining > 0, max(remaining - 1, 0)

    def _fetch_mailbox_threads(self, gmail: GmailService, *, include_bootstrap: bool) -> list[dict[str, Any]]:
        messages_by_id: dict[str, dict[str, Any]] = {}

        for message in gmail.list_messages(query=f"newer_than:{self.ACTIVE_GMAIL_DAYS}d", max_results=self.ACTIVE_GMAIL_MAX):
            if message.get("id"):
                messages_by_id[message["id"]] = message

        if include_bootstrap:
            for message in gmail.list_messages(
                query=f"newer_than:{self.BOOTSTRAP_GMAIL_DAYS}d",
                max_results=self.BOOTSTRAP_GMAIL_MAX,
            ):
                if message.get("id") and message["id"] not in messages_by_id:
                    messages_by_id[message["id"]] = message

        threads: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for message in messages_by_id.values():
            threads[message.get("threadId") or message.get("id") or "unknown"].append(message)

        thread_records: list[dict[str, Any]] = []
        for thread_id, messages in threads.items():
            sorted_messages = sorted(messages, key=self._message_sort_key)
            latest_stub = sorted_messages[-1]
            latest_full = gmail.get_message(latest_stub["id"]) or {}
            latest_message = {
                **latest_full,
                **latest_stub,
            }
            if latest_message.get("body"):
                latest_message["body"] = latest_message["body"][: self.MAX_EMAIL_BODY_CHARS]
            labels = {
                label
                for message in sorted_messages
                for label in (message.get("labelIds") or [])
            }
            thread_records.append(
                {
                    "thread_id": thread_id,
                    "messages": sorted_messages,
                    "latest_message": latest_message,
                    "unread": "UNREAD" in labels,
                    "important": "IMPORTANT" in labels,
                    "starred": "STARRED" in labels,
                }
            )

        return sorted(
            thread_records,
            key=lambda thread: self._message_sort_key(thread.get("latest_message") or {}),
            reverse=True,
        )

    def _fetch_drive_files(
        self,
        drive: DriveService,
        *,
        now: datetime,
        include_bootstrap: bool,
        folder_cache: dict[str, dict[str, Any]],
    ) -> list[dict[str, Any]]:
        active_since = (now - timedelta(days=self.ACTIVE_DRIVE_DAYS)).isoformat()
        bootstrap_since = (now - timedelta(days=self.BOOTSTRAP_DRIVE_DAYS)).isoformat()
        files_by_id: dict[str, dict[str, Any]] = {}

        def add_query_results(query: str, limit: int) -> None:
            response = drive.search_files(query=query, max_results=limit)
            for file in response.get("files", []):
                file_id = file.get("id")
                if not file_id or file.get("mimeType") == self.GOOGLE_FOLDER_MIME:
                    continue
                files_by_id.setdefault(file_id, file)

        add_query_results(
            self._drive_docs_query(active_since),
            min(self.ACTIVE_DRIVE_MAX, 60),
        )
        add_query_results(
            self._drive_text_like_query(active_since),
            min(self.ACTIVE_DRIVE_MAX, 40),
        )
        add_query_results(
            self._drive_general_query(active_since),
            self.ACTIVE_DRIVE_MAX,
        )

        if include_bootstrap:
            add_query_results(
                self._drive_docs_query(bootstrap_since),
                120,
            )
            add_query_results(
                self._drive_text_like_query(bootstrap_since),
                100,
            )
            add_query_results(
                self._drive_general_query(bootstrap_since),
                self.BOOTSTRAP_DRIVE_MAX,
            )

        enriched_files: list[dict[str, Any]] = []
        for file_id, base_file in files_by_id.items():
            full_file = drive.get_file(file_id) or {}
            file_data = {**base_file, **full_file}
            file_data["folder_path"] = drive.resolve_path(file_data.get("parents"), cache=folder_cache)
            if self._should_read_drive_content(file_data.get("mimeType")):
                content = drive.get_file_content(file_id)
                if content:
                    file_data["content_excerpt"] = content[: self.MAX_DRIVE_CONTENT_CHARS]
            enriched_files.append(file_data)

        return sorted(
            enriched_files,
            key=lambda file: file.get("modifiedTime") or "",
            reverse=True,
        )

    def _fetch_calendar_events(
        self,
        calendar: CalendarService,
        calendars: list[dict[str, Any]],
        *,
        now: datetime,
        include_bootstrap: bool,
    ) -> dict[str, list[dict[str, Any]]]:
        results: dict[str, list[dict[str, Any]]] = {}
        active_min = (now - timedelta(days=self.ACTIVE_CALENDAR_PAST_DAYS)).isoformat()
        active_max = (now + timedelta(days=self.ACTIVE_CALENDAR_FUTURE_DAYS)).isoformat()
        bootstrap_min = (now - timedelta(days=self.BOOTSTRAP_CALENDAR_PAST_DAYS)).isoformat()
        bootstrap_max = (now + timedelta(days=self.BOOTSTRAP_CALENDAR_FUTURE_DAYS)).isoformat()

        for cal in calendars:
            calendar_id = cal.get("id", "primary")
            events_by_id: dict[str, dict[str, Any]] = {}
            for event in calendar.list_events(
                calendar_id=calendar_id,
                time_min=active_min,
                time_max=active_max,
                max_results=self.ACTIVE_CALENDAR_MAX,
            ):
                if event.get("id"):
                    events_by_id[event["id"]] = event
            if include_bootstrap:
                for event in calendar.list_events(
                    calendar_id=calendar_id,
                    time_min=bootstrap_min,
                    time_max=bootstrap_max,
                    max_results=self.BOOTSTRAP_CALENDAR_MAX,
                ):
                    if event.get("id") and event["id"] not in events_by_id:
                        events_by_id[event["id"]] = event

            results[calendar_id] = sorted(
                events_by_id.values(),
                key=lambda event: self._event_start_sort_key(event),
            )

        return results

    def _select_calendars(self, calendars: list[dict[str, Any]]) -> list[dict[str, Any]]:
        primary = [calendar for calendar in calendars if calendar.get("primary")]
        non_primary = [calendar for calendar in calendars if not calendar.get("primary")]
        return (primary[:1] + non_primary[: self.MAX_CALENDARS - 1])[: self.MAX_CALENDARS]

    def _drive_docs_query(self, modified_since: str) -> str:
        return (
            "trashed = false "
            f"and modifiedTime >= '{modified_since}' "
            f"and mimeType = '{self.GOOGLE_DOC_MIME}'"
        )

    def _drive_text_like_query(self, modified_since: str) -> str:
        mime_filters = " or ".join(f"mimeType = '{mime}'" for mime in sorted(self.TEXT_LIKE_MIME_TYPES))
        return f"trashed = false and modifiedTime >= '{modified_since}' and ({mime_filters})"

    def _drive_general_query(self, modified_since: str) -> str:
        return (
            "trashed = false "
            f"and modifiedTime >= '{modified_since}' "
            f"and mimeType != '{self.GOOGLE_FOLDER_MIME}'"
        )

    def _should_read_drive_content(self, mime_type: Optional[str]) -> bool:
        if not mime_type:
            return False
        return mime_type == self.GOOGLE_DOC_MIME or mime_type in self.TEXT_LIKE_MIME_TYPES

    def _extract_message_people(self, messages: Iterable[dict]) -> list[str]:
        participants: list[str] = []
        for message in messages:
            raw_addresses = [message.get("from", ""), message.get("to", ""), message.get("cc", "")]
            for _, email in getaddresses(raw_addresses):
                if email and email not in participants:
                    participants.append(email)
        return participants

    def _message_sort_key(self, message: dict[str, Any]) -> datetime:
        if message.get("internalDate"):
            try:
                return datetime.fromtimestamp(int(message["internalDate"]) / 1000, tz=timezone.utc)
            except (TypeError, ValueError):
                pass
        if message.get("date"):
            try:
                parsed = parsedate_to_datetime(message["date"])
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=timezone.utc)
                return parsed.astimezone(timezone.utc)
            except (TypeError, ValueError, IndexError):
                pass
        return datetime.min.replace(tzinfo=timezone.utc)

    def _message_updated_at(self, message: dict[str, Any]) -> Optional[str]:
        dt = self._message_sort_key(message)
        if dt == datetime.min.replace(tzinfo=timezone.utc):
            return None
        return dt.isoformat()

    def _is_external_thread(self, participants: Iterable[str], account_email: Optional[str]) -> bool:
        if not account_email or "@" not in account_email:
            return bool(participants)
        own_domain = account_email.split("@", 1)[1].lower()
        own_email = account_email.lower()
        for participant in participants:
            normalized = participant.lower()
            if normalized == own_email:
                continue
            if "@" not in normalized:
                return True
            if normalized.split("@", 1)[1] != own_domain:
                return True
        return False

    def _upsert_identifier_people(
        self,
        people_map: Dict[str, SnapshotPerson],
        identifiers: Iterable[str],
        *,
        related_entity: str,
        role: str,
    ) -> None:
        for identifier in identifiers:
            if not identifier:
                continue
            person = people_map.get(identifier)
            if person is None:
                person = SnapshotPerson(
                    identifier=identifier,
                    display_name=identifier,
                    role=role,
                    related_entities=[],
                )
                people_map[identifier] = person
            if related_entity not in person.related_entities:
                person.related_entities.append(related_entity)

    def _upsert_google_people(
        self,
        people_map: Dict[str, SnapshotPerson],
        people: Iterable[dict[str, Any]],
        *,
        related_entity: str,
        role: str,
    ) -> None:
        for person in people:
            if not isinstance(person, dict):
                continue
            identifier = person.get("emailAddress") or person.get("email") or person.get("displayName")
            display_name = self._google_person_display(person)
            if not identifier or not display_name:
                continue
            existing = people_map.get(identifier)
            if existing is None:
                existing = SnapshotPerson(
                    identifier=identifier,
                    display_name=display_name,
                    role=role,
                    related_entities=[],
                )
                people_map[identifier] = existing
            if related_entity not in existing.related_entities:
                existing.related_entities.append(related_entity)

    def _google_person_display(self, person: Any) -> str:
        if not isinstance(person, dict):
            return ""
        return person.get("displayName") or person.get("emailAddress") or person.get("email") or ""

    def _people_from_google_people(self, people: Iterable[dict[str, Any]]) -> list[str]:
        results: list[str] = []
        for person in people:
            display = self._google_person_display(person)
            if display and display not in results:
                results.append(display)
        return results

    def _ensure_drive_folder_container(
        self,
        folder_id: str,
        folders_by_id: dict[str, dict[str, Any]],
        containers_by_id: dict[str, SnapshotContainer],
    ) -> str:
        current = folders_by_id.get(folder_id) or {}
        if not current:
            return "gdrive:root"
        container_id = f"gdrive:folder:{folder_id}"
        if container_id in containers_by_id:
            return container_id

        parents = current.get("parents") or []
        parent_container_id = "gdrive:root"
        if parents and parents[0] != "root" and parents[0] in folders_by_id:
            parent_container_id = self._ensure_drive_folder_container(
                parents[0],
                folders_by_id,
                containers_by_id,
            )

        containers_by_id[container_id] = SnapshotContainer(
            container_type="folder",
            container_id=container_id,
            title=current.get("name") or folder_id,
            parent_id=parent_container_id,
            source_url=current.get("webViewLink"),
        )
        return container_id

    def _resolve_drive_container_id(
        self,
        parents: Optional[list[str]],
        folders_by_id: dict[str, dict[str, Any]],
    ) -> str:
        if not parents:
            return "gdrive:root"
        primary_parent = parents[0]
        if primary_parent == "root":
            return "gdrive:root"
        if primary_parent in folders_by_id:
            return f"gdrive:folder:{primary_parent}"
        return "gdrive:root"

    def _drive_project(self, folder_path: str, entity_type: str) -> str:
        parts = [part for part in folder_path.split("/") if part]
        if parts:
            return parts[0]
        return "docs" if entity_type == "doc" else "drive"

    def _calendar_people(self, event: dict[str, Any]) -> list[str]:
        people: list[str] = []
        for person in self._calendar_people_dicts(event):
            display = self._google_person_display(person)
            if display and display not in people:
                people.append(display)
        return people

    def _calendar_people_dicts(self, event: dict[str, Any]) -> list[dict[str, Any]]:
        people: list[dict[str, Any]] = []
        for person in [
            *((event.get("attendees") or [])),
            event.get("creator") or {},
            event.get("organizer") or {},
        ]:
            if isinstance(person, dict) and person:
                people.append(person)
        return people

    def _event_start_sort_key(self, event: dict[str, Any]) -> datetime:
        start = (event.get("start") or {}).get("dateTime") or (event.get("start") or {}).get("date")
        parsed = self._parse_datetime(start)
        if parsed:
            return parsed
        return datetime.max.replace(tzinfo=timezone.utc)

    def _parse_datetime(self, value: Optional[str]) -> Optional[datetime]:
        if not value:
            return None
        try:
            if len(value) == 10:
                return datetime.fromisoformat(value + "T00:00:00+00:00")
            if value.endswith("Z"):
                value = value[:-1] + "+00:00"
            dt = datetime.fromisoformat(value)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except ValueError:
            return None

    def _is_recent(self, value: Optional[str], since_marker: Optional[str]) -> bool:
        dt = self._parse_datetime(value)
        since = self._parse_datetime(since_marker)
        return bool(dt and since and dt >= since)

    def _is_older_than(self, value: Optional[str], *, hours: int) -> bool:
        dt = self._parse_datetime(value)
        if not dt:
            return False
        return datetime.now(timezone.utc) - dt >= timedelta(hours=hours)

    def _is_upcoming(
        self,
        event: dict[str, Any],
        *,
        within_days: Optional[int] = None,
        within_hours: Optional[int] = None,
    ) -> bool:
        start = (event.get("start") or {}).get("dateTime") or (event.get("start") or {}).get("date")
        start_dt = self._parse_datetime(start)
        if not start_dt:
            return False
        now = datetime.now(timezone.utc)
        if start_dt < now:
            return False
        if within_hours is not None:
            return start_dt <= now + timedelta(hours=within_hours)
        if within_days is not None:
            return start_dt <= now + timedelta(days=within_days)
        return False
