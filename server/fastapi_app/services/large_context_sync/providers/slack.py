"""Slack large-context provider.

Pulls the latest conversations from Slack channels/DMs the bot has access to
and turns them into the shared large-context snapshot shape.

Design notes
------------
* We use a **bot token**, so we can only see public/private channels the bot
  has been invited to plus DMs involving the bot. That is a Slack platform
  limitation, not a bug.
* Slack generates *a lot* of messages. We deliberately do **not** persist raw
  messages as entities. Instead, per channel, we:
    * Collapse every ``thread_ts`` into a single ``slack_thread`` entity.
    * Bucket remaining top-level chatter into ``slack_chunk`` entities using
      a time-gap heuristic (new chunk whenever there's a long silence or the
      chunk grows too large). The snapshot carries a short summary of each
      chunk, not the raw messages.
* A cursor tracks the latest seen ``ts`` per channel so subsequent runs only
  pull new messages. The first couple of runs pull a wider window to
  "bootstrap" historical context, mirroring the Google Workspace provider.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple

from covalent_mcp.toolclasses.issue_tracker.common import extract_external_references
from covalent_mcp.toolclasses.slack.slack_client import SlackAPIError, SlackClient
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


class SlackLargeContextProvider(LargeContextProvider):
    provider_id = "slack"
    display_name = "Slack"
    supports_live_sync = True
    file_name = "slack.md"
    integration_provider_key = "slack"

    # How many member channels we sync per run. Slack workspaces are often
    # enormous; picking the top N by recency keeps rate-limit pressure sane.
    MAX_CHANNELS_ACTIVE = 20
    MAX_CHANNELS_BOOTSTRAP = 30

    ACTIVE_HISTORY_DAYS = 14
    BOOTSTRAP_HISTORY_DAYS = 30

    # Per-channel history caps. Threads pull their own replies on top of these.
    MAX_HISTORY_MESSAGES_ACTIVE = 200
    MAX_HISTORY_MESSAGES_BOOTSTRAP = 500
    MAX_REPLIES_PER_THREAD = 200

    # Topic-chunking heuristics for non-threaded chatter.
    CHUNK_GAP_MINUTES = 30
    CHUNK_MAX_MESSAGES = 25

    # Text trimming for summaries stored in the snapshot.
    MAX_MESSAGE_TEXT = 1200
    MAX_SUMMARY_TEXT = 1200

    def __init__(self, integration_dao: IntegrationDAO):
        self.integration_dao = integration_dao

    # ------------------------------------------------------------------
    # Connection + fetch
    # ------------------------------------------------------------------

    def is_connected(self, integration_dao) -> bool:
        token = integration_dao.get_token("slack")
        return bool(token and token.get("access_token"))

    def fetch_delta(self, cursor: Optional[dict], since_ts: str) -> ProviderFetchResult:
        token = self.integration_dao.get_token("slack")
        if not token or not token.get("access_token"):
            raise RuntimeError("Slack integration is not connected")

        cursor = cursor or {}
        channel_cursors: Dict[str, str] = dict(cursor.get("channels") or {})
        include_bootstrap, next_bootstrap_remaining = self._bootstrap_state(cursor)

        client = SlackClient(token["access_token"])
        workspace = self._fetch_workspace(client, token)
        users_by_id = self._fetch_users(client)
        channels = self._fetch_member_conversations(client, include_bootstrap=include_bootstrap)

        history_cutoff = datetime.now(timezone.utc) - timedelta(
            days=self.BOOTSTRAP_HISTORY_DAYS if include_bootstrap else self.ACTIVE_HISTORY_DAYS
        )
        history_cutoff_ts = f"{history_cutoff.timestamp():.6f}"
        max_messages = (
            self.MAX_HISTORY_MESSAGES_BOOTSTRAP
            if include_bootstrap
            else self.MAX_HISTORY_MESSAGES_ACTIVE
        )

        channel_records: List[Dict[str, Any]] = []
        new_channel_cursors: Dict[str, str] = {}
        for channel in channels:
            channel_id = channel.get("id")
            if not channel_id:
                continue
            previous_ts = channel_cursors.get(channel_id)
            oldest = self._max_ts(previous_ts, history_cutoff_ts)
            try:
                messages = list(
                    client.iter_history(
                        channel_id,
                        oldest=oldest,
                        max_messages=max_messages,
                    )
                )
            except SlackAPIError as exc:
                log.warning(
                    f"Slack history fetch failed for channel={channel_id} error={exc.error}; skipping"
                )
                if previous_ts:
                    new_channel_cursors[channel_id] = previous_ts
                continue

            thread_replies = self._fetch_thread_replies(
                client,
                channel_id,
                messages,
                oldest=oldest,
            )

            latest_ts = self._latest_ts(messages, thread_replies, fallback=previous_ts)
            if latest_ts:
                new_channel_cursors[channel_id] = latest_ts
            elif previous_ts:
                new_channel_cursors[channel_id] = previous_ts

            channel_records.append(
                {
                    "channel": channel,
                    "messages": messages,
                    "thread_replies": thread_replies,
                }
            )

        return ProviderFetchResult(
            records=[
                {
                    "workspace": workspace,
                    "users_by_id": users_by_id,
                    "channels": channel_records,
                }
            ],
            next_cursor={
                "channels": new_channel_cursors,
                "bootstrap_remaining": next_bootstrap_remaining,
            },
            metadata={
                "backfill_since": (cursor.get("since") if isinstance(cursor, dict) else None) or since_ts,
                "team_id": workspace.get("team_id"),
                "team_name": workspace.get("team"),
                "bootstrap_included": include_bootstrap,
                "channels_synced": len(channel_records),
            },
        )

    # ------------------------------------------------------------------
    # Snapshot building
    # ------------------------------------------------------------------

    def build_snapshot(
        self,
        fetch_result: ProviderFetchResult,
        previous_snapshot: ProviderSnapshot | None = None,
    ) -> ProviderSnapshot:
        record = fetch_result.records[0] if fetch_result.records else {}
        workspace = record.get("workspace") or {}
        users_by_id: Dict[str, Dict[str, Any]] = record.get("users_by_id") or {}
        channel_records: List[Dict[str, Any]] = record.get("channels") or []

        team_id = workspace.get("team_id") or "unknown"
        team_name = workspace.get("team") or "Slack Workspace"
        team_url = (workspace.get("url") or "").rstrip("/")

        workspace_container_id = f"slack:team:{team_id}"
        containers_by_id: Dict[str, SnapshotContainer] = {
            workspace_container_id: SnapshotContainer(
                container_type="workspace",
                container_id=workspace_container_id,
                title=team_name,
                source_url=team_url or None,
            )
        }

        entities: List[SnapshotEntity] = []
        people_map: Dict[str, SnapshotPerson] = {}
        cross_links: List[SnapshotCrossLink] = []
        open_questions: List[str] = []
        watch_items: List[str] = []

        since_marker = fetch_result.metadata.get("backfill_since")
        bot_user_id = workspace.get("user_id")

        for channel_record in channel_records:
            channel = channel_record.get("channel") or {}
            channel_id = channel.get("id")
            if not channel_id:
                continue
            container_id = f"slack:channel:{channel_id}"
            containers_by_id[container_id] = self._build_channel_container(
                channel,
                users_by_id=users_by_id,
                parent_id=workspace_container_id,
                team_url=team_url,
            )

            thread_groups, standalone = self._group_messages(
                messages=channel_record.get("messages") or [],
                thread_replies=channel_record.get("thread_replies") or {},
            )

            channel_display = self._channel_display_name(channel, users_by_id)
            channel_project = self._channel_project(channel)

            for thread_ts, thread_messages in thread_groups.items():
                thread_entity = self._build_thread_entity(
                    channel=channel,
                    channel_id=channel_id,
                    thread_ts=thread_ts,
                    thread_messages=thread_messages,
                    users_by_id=users_by_id,
                    container_id=container_id,
                    team_url=team_url,
                    project=channel_project,
                )
                entities.append(thread_entity)
                self._upsert_people(
                    people_map,
                    self._collect_user_ids(thread_messages),
                    users_by_id=users_by_id,
                    related_entity=thread_entity.external_id,
                    role="slack_participant",
                )
                for target in thread_entity.related_entities:
                    cross_links.append(
                        SnapshotCrossLink(
                            source_entity_id=thread_entity.external_id,
                            target_entity_id=target,
                            relationship="references",
                        )
                    )
                self._score_thread_for_hints(
                    thread_entity=thread_entity,
                    thread_messages=thread_messages,
                    channel_display=channel_display,
                    bot_user_id=bot_user_id,
                    since_marker=since_marker,
                    open_questions=open_questions,
                    watch_items=watch_items,
                )

            for chunk_messages in self._topic_chunks(standalone):
                chunk_entity = self._build_chunk_entity(
                    channel=channel,
                    channel_id=channel_id,
                    chunk_messages=chunk_messages,
                    users_by_id=users_by_id,
                    container_id=container_id,
                    team_url=team_url,
                    project=channel_project,
                )
                entities.append(chunk_entity)
                self._upsert_people(
                    people_map,
                    self._collect_user_ids(chunk_messages),
                    users_by_id=users_by_id,
                    related_entity=chunk_entity.external_id,
                    role="slack_participant",
                )
                for target in chunk_entity.related_entities:
                    cross_links.append(
                        SnapshotCrossLink(
                            source_entity_id=chunk_entity.external_id,
                            target_entity_id=target,
                            relationship="references",
                        )
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

    # ------------------------------------------------------------------
    # Fetch helpers
    # ------------------------------------------------------------------

    def _bootstrap_state(self, cursor: Dict[str, Any]) -> Tuple[bool, int]:
        if "bootstrap_remaining" not in cursor:
            return True, 2
        try:
            remaining = max(int(cursor.get("bootstrap_remaining") or 0), 0)
        except (TypeError, ValueError):
            return True, 2
        return remaining > 0, max(remaining - 1, 0)

    def _fetch_workspace(self, client: SlackClient, token: Dict[str, Any]) -> Dict[str, Any]:
        workspace: Dict[str, Any] = {}
        try:
            workspace.update(client.auth_test())
        except SlackAPIError as exc:
            log.warning(f"Slack auth.test failed: {exc.error}")
        try:
            team = client.team_info()
        except SlackAPIError as exc:
            log.warning(f"Slack team.info failed: {exc.error}; falling back to auth.test metadata")
            team = {}
        if team:
            workspace.setdefault("team_id", team.get("id"))
            workspace.setdefault("team", team.get("name"))
            workspace.setdefault("url", team.get("url"))
            workspace["team_domain"] = team.get("domain")
            workspace["team_icon"] = (team.get("icon") or {}).get("image_132")
        metadata = token.get("provider_metadata") or {}
        for key in ("team_id", "team", "url"):
            if not workspace.get(key) and metadata.get(key):
                workspace[key] = metadata[key]
        return workspace

    def _fetch_users(self, client: SlackClient) -> Dict[str, Dict[str, Any]]:
        users: Dict[str, Dict[str, Any]] = {}
        try:
            for user in client.iter_users():
                user_id = user.get("id")
                if not user_id:
                    continue
                if user.get("deleted"):
                    continue
                users[user_id] = user
        except SlackAPIError as exc:
            log.warning(f"Slack users.list failed: {exc.error}")
        return users

    def _fetch_member_conversations(
        self,
        client: SlackClient,
        *,
        include_bootstrap: bool,
    ) -> List[Dict[str, Any]]:
        try:
            all_channels = client.list_all_conversations(
                types=("public_channel", "private_channel", "mpim", "im"),
                exclude_archived=True,
            )
        except SlackAPIError as exc:
            log.warning(f"Slack conversations.list failed: {exc.error}")
            return []

        member_channels = [
            channel
            for channel in all_channels
            if channel.get("is_im")
            or channel.get("is_mpim")
            or channel.get("is_member")
        ]
        ranked = sorted(
            member_channels,
            key=lambda channel: self._channel_activity_sort_key(channel),
            reverse=True,
        )
        cap = self.MAX_CHANNELS_BOOTSTRAP if include_bootstrap else self.MAX_CHANNELS_ACTIVE
        return ranked[:cap]

    def _fetch_thread_replies(
        self,
        client: SlackClient,
        channel_id: str,
        messages: Iterable[Dict[str, Any]],
        *,
        oldest: Optional[str],
    ) -> Dict[str, List[Dict[str, Any]]]:
        replies_by_ts: Dict[str, List[Dict[str, Any]]] = {}
        for message in messages:
            ts = message.get("ts")
            thread_ts = message.get("thread_ts")
            if not ts or thread_ts != ts:
                continue
            if int(message.get("reply_count") or 0) <= 0:
                continue
            try:
                fetched = list(
                    client.iter_replies(
                        channel_id,
                        ts,
                        oldest=oldest,
                        max_messages=self.MAX_REPLIES_PER_THREAD,
                    )
                )
            except SlackAPIError as exc:
                log.warning(
                    f"Slack conversations.replies failed for channel={channel_id} thread={ts}: {exc.error}"
                )
                continue
            # ``conversations.replies`` always echoes the parent as the first
            # element — drop it so we don't double-count.
            replies_by_ts[ts] = [reply for reply in fetched if reply.get("ts") != ts]
        return replies_by_ts

    # ------------------------------------------------------------------
    # Snapshot helpers
    # ------------------------------------------------------------------

    def _build_channel_container(
        self,
        channel: Dict[str, Any],
        *,
        users_by_id: Dict[str, Dict[str, Any]],
        parent_id: str,
        team_url: str,
    ) -> SnapshotContainer:
        channel_id = channel.get("id") or "unknown"
        title = self._channel_display_name(channel, users_by_id)
        container_type = "dm" if channel.get("is_im") else "group_dm" if channel.get("is_mpim") else "channel"
        return SnapshotContainer(
            container_type=container_type,
            container_id=f"slack:channel:{channel_id}",
            title=title,
            parent_id=parent_id,
            source_url=self._channel_url(channel_id, team_url),
            summary=(channel.get("purpose") or {}).get("value") or (channel.get("topic") or {}).get("value") or None,
        )

    def _group_messages(
        self,
        *,
        messages: List[Dict[str, Any]],
        thread_replies: Dict[str, List[Dict[str, Any]]],
    ) -> Tuple[Dict[str, List[Dict[str, Any]]], List[Dict[str, Any]]]:
        """Split channel history into thread groups + standalone messages.

        A message is considered part of a thread if it has a ``thread_ts``
        pointing at another message. Thread parents with no replies are
        treated as standalone chatter so they can be merged into a topic
        chunk alongside their neighbors.
        """
        thread_groups: Dict[str, List[Dict[str, Any]]] = {}
        standalone: List[Dict[str, Any]] = []

        for message in messages:
            if message.get("subtype") in {"channel_join", "channel_leave", "bot_add", "bot_remove"}:
                continue
            ts = message.get("ts")
            if not ts:
                continue
            thread_ts = message.get("thread_ts")
            reply_count = int(message.get("reply_count") or 0)

            is_thread_parent = thread_ts == ts and reply_count > 0
            is_reply = bool(thread_ts) and thread_ts != ts

            if is_thread_parent:
                bucket = thread_groups.setdefault(thread_ts, [])
                bucket.append(message)
                for reply in thread_replies.get(thread_ts, []):
                    bucket.append(reply)
            elif is_reply:
                thread_groups.setdefault(thread_ts, []).append(message)
            else:
                standalone.append(message)

        for ts, thread_messages in thread_groups.items():
            thread_groups[ts] = self._dedupe_and_sort_messages(thread_messages)

        standalone.sort(key=self._message_ts_sort_key)
        return thread_groups, standalone

    def _topic_chunks(self, messages: List[Dict[str, Any]]) -> List[List[Dict[str, Any]]]:
        """Split a stream of messages into topic chunks using a time-gap heuristic.

        A new chunk starts whenever the silence since the previous message
        exceeds ``CHUNK_GAP_MINUTES`` or the chunk would exceed
        ``CHUNK_MAX_MESSAGES`` messages.
        """
        if not messages:
            return []
        chunks: List[List[Dict[str, Any]]] = []
        current: List[Dict[str, Any]] = []
        gap = timedelta(minutes=self.CHUNK_GAP_MINUTES)
        previous_dt: Optional[datetime] = None
        for message in messages:
            dt = self._ts_to_datetime(message.get("ts"))
            start_new = (
                not current
                or (previous_dt is not None and dt is not None and dt - previous_dt > gap)
                or len(current) >= self.CHUNK_MAX_MESSAGES
            )
            if start_new and current:
                chunks.append(current)
                current = []
            current.append(message)
            if dt is not None:
                previous_dt = dt
        if current:
            chunks.append(current)
        return chunks

    def _build_thread_entity(
        self,
        *,
        channel: Dict[str, Any],
        channel_id: str,
        thread_ts: str,
        thread_messages: List[Dict[str, Any]],
        users_by_id: Dict[str, Dict[str, Any]],
        container_id: str,
        team_url: str,
        project: Optional[str],
    ) -> SnapshotEntity:
        parent = thread_messages[0] if thread_messages else {}
        parent_text = self._message_text(parent)
        title = self._short_title(parent_text) or f"Slack thread {thread_ts}"
        participants = [
            self._user_display(user_id, users_by_id)
            for user_id in self._collect_user_ids(thread_messages)
        ]
        body_texts = [self._message_text(m) for m in thread_messages]
        refs = extract_external_references(body_texts)
        related = [*refs["github"], *refs["jira"], *refs["slack"], *refs["notion"]]
        summary = "\n".join(text for text in body_texts if text)[: self.MAX_SUMMARY_TEXT]
        updated_at = self._iso_from_ts(
            max(
                (m.get("ts") for m in thread_messages if m.get("ts")),
                default=thread_ts,
            )
        )
        external_id = f"slack:{channel_id}:{thread_ts}"

        return SnapshotEntity(
            entity_type="slack_thread",
            external_id=external_id,
            title=title,
            status="active",
            summary=summary,
            project=project,
            feature_tags=[],
            people=participants,
            related_entities=related,
            updated_at=updated_at,
            source_url=self._message_url(channel_id, thread_ts, team_url),
            container_id=container_id,
            extra_fields={
                "channel_id": channel_id,
                "channel_name": channel.get("name") or channel.get("id") or "",
                "thread_ts": thread_ts,
                "reply_count": max(len(thread_messages) - 1, 0),
                "participants": participants,
                "is_dm": bool(channel.get("is_im")),
                "is_private": bool(channel.get("is_private") and not channel.get("is_im")),
            },
        )

    def _build_chunk_entity(
        self,
        *,
        channel: Dict[str, Any],
        channel_id: str,
        chunk_messages: List[Dict[str, Any]],
        users_by_id: Dict[str, Dict[str, Any]],
        container_id: str,
        team_url: str,
        project: Optional[str],
    ) -> SnapshotEntity:
        first = chunk_messages[0]
        last = chunk_messages[-1]
        first_ts = first.get("ts") or ""
        last_ts = last.get("ts") or first_ts
        participants = [
            self._user_display(user_id, users_by_id)
            for user_id in self._collect_user_ids(chunk_messages)
        ]
        body_texts = [self._message_text(m) for m in chunk_messages]
        refs = extract_external_references(body_texts)
        related = [*refs["github"], *refs["jira"], *refs["slack"], *refs["notion"]]
        summary = "\n".join(text for text in body_texts if text)[: self.MAX_SUMMARY_TEXT]
        channel_label = self._channel_display_name(channel, users_by_id)
        started_at_iso = self._iso_from_ts(first_ts)
        title = self._short_title(body_texts[0] if body_texts else "") or (
            f"Discussion in {channel_label}"
            + (f" at {started_at_iso}" if started_at_iso else "")
        )
        external_id = f"slack:{channel_id}:chunk:{first_ts}"

        return SnapshotEntity(
            entity_type="slack_chunk",
            external_id=external_id,
            title=title,
            status="active",
            summary=summary,
            project=project,
            feature_tags=["firehose"] if len(chunk_messages) >= self.CHUNK_MAX_MESSAGES else [],
            people=participants,
            related_entities=related,
            updated_at=self._iso_from_ts(last_ts),
            source_url=self._message_url(channel_id, first_ts, team_url),
            container_id=container_id,
            extra_fields={
                "channel_id": channel_id,
                "channel_name": channel.get("name") or channel.get("id") or "",
                "started_at": started_at_iso,
                "ended_at": self._iso_from_ts(last_ts),
                "message_count": len(chunk_messages),
                "participants": participants,
            },
        )

    def _score_thread_for_hints(
        self,
        *,
        thread_entity: SnapshotEntity,
        thread_messages: List[Dict[str, Any]],
        channel_display: str,
        bot_user_id: Optional[str],
        since_marker: Optional[str],
        open_questions: List[str],
        watch_items: List[str],
    ) -> None:
        if not thread_messages:
            return
        parent = thread_messages[0]
        mentions = self._collect_mentions(thread_messages)
        if bot_user_id and bot_user_id in mentions:
            open_questions.append(
                f"Slack thread mentions you in {channel_display}: {thread_entity.title}"
            )
        if thread_entity.related_entities and self._is_recent(thread_entity.updated_at, since_marker):
            watch_items.append(
                f"Active Slack thread linked to outside work: {thread_entity.title}"
            )
        if (
            len(thread_messages) >= 10
            and self._is_older_than(self._iso_from_ts(parent.get("ts")), hours=48)
        ):
            watch_items.append(
                f"Long-running Slack thread aging without resolution: {thread_entity.title}"
            )

    # ------------------------------------------------------------------
    # Presentation + identity helpers
    # ------------------------------------------------------------------

    def _channel_display_name(
        self,
        channel: Dict[str, Any],
        users_by_id: Dict[str, Dict[str, Any]],
    ) -> str:
        if channel.get("is_im"):
            user = users_by_id.get(channel.get("user") or "", {})
            display = self._user_display(channel.get("user") or "", users_by_id) or "unknown"
            return f"DM with {display}" if display else f"DM {user.get('id') or channel.get('id')}"
        if channel.get("is_mpim"):
            return channel.get("name") or channel.get("name_normalized") or "Group DM"
        name = channel.get("name") or channel.get("name_normalized")
        return f"#{name}" if name else channel.get("id") or "Channel"

    def _channel_project(self, channel: Dict[str, Any]) -> Optional[str]:
        if channel.get("is_im") or channel.get("is_mpim"):
            return "slack-dms"
        return channel.get("name") or channel.get("name_normalized") or "slack"

    def _channel_activity_sort_key(self, channel: Dict[str, Any]) -> float:
        # ``latest`` is populated by conversations.list when the caller has
        # at least one message visible. Fall back to membership + num_members
        # so sparse channels still rank deterministically.
        latest = (channel.get("latest") or {}).get("ts")
        if latest:
            try:
                return float(latest)
            except (TypeError, ValueError):
                pass
        updated = channel.get("updated")
        if isinstance(updated, (int, float)):
            return float(updated) / 1000.0
        return float(channel.get("num_members") or 0)

    def _channel_url(self, channel_id: str, team_url: str) -> Optional[str]:
        if not team_url:
            return None
        return f"{team_url.rstrip('/')}/archives/{channel_id}"

    def _message_url(self, channel_id: str, ts: str, team_url: str) -> Optional[str]:
        if not team_url or not ts:
            return None
        compact = ts.replace(".", "")
        return f"{team_url.rstrip('/')}/archives/{channel_id}/p{compact}"

    def _collect_user_ids(self, messages: Iterable[Dict[str, Any]]) -> List[str]:
        seen: List[str] = []
        for message in messages:
            user_id = message.get("user") or message.get("bot_id")
            if user_id and user_id not in seen:
                seen.append(user_id)
        return seen

    def _collect_mentions(self, messages: Iterable[Dict[str, Any]]) -> set[str]:
        mentions: set[str] = set()
        for message in messages:
            text = message.get("text") or ""
            # Slack renders mentions as ``<@U123456>``. Cheap scan to avoid
            # pulling in a dedicated regex for such a simple pattern.
            index = 0
            while True:
                start = text.find("<@", index)
                if start < 0:
                    break
                end = text.find(">", start)
                if end < 0:
                    break
                token = text[start + 2 : end]
                pipe = token.find("|")
                if pipe >= 0:
                    token = token[:pipe]
                if token:
                    mentions.add(token)
                index = end + 1
        return mentions

    def _upsert_people(
        self,
        people_map: Dict[str, SnapshotPerson],
        user_ids: Iterable[str],
        *,
        users_by_id: Dict[str, Dict[str, Any]],
        related_entity: str,
        role: str,
    ) -> None:
        for user_id in user_ids:
            if not user_id:
                continue
            display = self._user_display(user_id, users_by_id) or user_id
            person = people_map.get(user_id)
            if person is None:
                person = SnapshotPerson(
                    identifier=user_id,
                    display_name=display,
                    role=role,
                    related_entities=[],
                )
                people_map[user_id] = person
            if related_entity not in person.related_entities:
                person.related_entities.append(related_entity)

    def _user_display(self, user_id: str, users_by_id: Dict[str, Dict[str, Any]]) -> str:
        user = users_by_id.get(user_id) or {}
        profile = user.get("profile") or {}
        return (
            profile.get("display_name_normalized")
            or profile.get("display_name")
            or profile.get("real_name_normalized")
            or profile.get("real_name")
            or user.get("real_name")
            or user.get("name")
            or user_id
        )

    def _message_text(self, message: Dict[str, Any]) -> str:
        text = (message.get("text") or "").strip()
        if not text:
            return ""
        return text[: self.MAX_MESSAGE_TEXT]

    def _short_title(self, text: str) -> str:
        if not text:
            return ""
        first_line = text.strip().splitlines()[0]
        return first_line[:120]

    def _dedupe_and_sort_messages(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        seen: set[str] = set()
        unique: List[Dict[str, Any]] = []
        for message in messages:
            ts = message.get("ts")
            if not ts or ts in seen:
                continue
            seen.add(ts)
            unique.append(message)
        unique.sort(key=self._message_ts_sort_key)
        return unique

    def _latest_ts(
        self,
        messages: Iterable[Dict[str, Any]],
        thread_replies: Dict[str, List[Dict[str, Any]]],
        *,
        fallback: Optional[str],
    ) -> Optional[str]:
        best: Optional[float] = None
        best_raw: Optional[str] = fallback
        for message in messages:
            ts = message.get("ts")
            value = self._ts_to_float(ts)
            if value is not None and (best is None or value > best):
                best = value
                best_raw = ts
        for replies in thread_replies.values():
            for reply in replies:
                ts = reply.get("ts")
                value = self._ts_to_float(ts)
                if value is not None and (best is None or value > best):
                    best = value
                    best_raw = ts
        return best_raw

    # ------------------------------------------------------------------
    # Timestamp helpers (Slack uses unix seconds with microsecond suffix)
    # ------------------------------------------------------------------

    def _ts_to_float(self, ts: Optional[str]) -> Optional[float]:
        if not ts:
            return None
        try:
            return float(ts)
        except (TypeError, ValueError):
            return None

    def _ts_to_datetime(self, ts: Optional[str]) -> Optional[datetime]:
        value = self._ts_to_float(ts)
        if value is None:
            return None
        return datetime.fromtimestamp(value, tz=timezone.utc)

    def _iso_from_ts(self, ts: Optional[str]) -> Optional[str]:
        dt = self._ts_to_datetime(ts)
        return dt.isoformat() if dt else None

    def _message_ts_sort_key(self, message: Dict[str, Any]) -> float:
        return self._ts_to_float(message.get("ts")) or 0.0

    def _max_ts(self, *values: Optional[str]) -> Optional[str]:
        best_raw: Optional[str] = None
        best_float: Optional[float] = None
        for value in values:
            as_float = self._ts_to_float(value)
            if as_float is None:
                continue
            if best_float is None or as_float > best_float:
                best_float = as_float
                best_raw = value
        return best_raw

    def _parse_iso(self, value: Optional[str]) -> Optional[datetime]:
        if not value:
            return None
        try:
            text = value[:-1] + "+00:00" if value.endswith("Z") else value
            parsed = datetime.fromisoformat(text)
        except ValueError:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    def _is_recent(self, value: Optional[str], since_marker: Optional[str]) -> bool:
        dt = self._parse_iso(value)
        since = self._parse_iso(since_marker)
        return bool(dt and since and dt >= since)

    def _is_older_than(self, value: Optional[str], *, hours: int) -> bool:
        dt = self._parse_iso(value)
        if not dt:
            return False
        return datetime.now(timezone.utc) - dt >= timedelta(hours=hours)
