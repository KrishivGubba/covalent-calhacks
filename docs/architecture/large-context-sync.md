# Large Context Sync

## Goal
Large context sync extends Covalent beyond screen-only context. The screen is still the proactive trigger surface, but the agent also needs durable context from the PM's systems of work: GitHub, Google Workspace, Notion, Slack, Jira, and future integrations.

The loop exists to keep a brief, structured, on-device long-term snapshot of those systems so the agent can quickly understand:
- active issues, PRs, tickets, docs, and message threads
- the projects/features they belong to
- the people involved
- cross-links between systems

## Lifecycle
`large_context_sync` is a FastAPI-owned background loop.

For each scheduled run:
1. Load persisted sync config and provider state.
2. Iterate the provider registry one provider at a time.
3. Skip disconnected live providers and placeholder-only providers cleanly.
4. Fetch deltas using the saved cursor or an initial backfill window.
5. Normalize the provider data into a snapshot model.
6. Write the provider markdown snapshot atomically to disk.
7. Project high-signal entities into the dedicated graph subtree.
8. Persist cursor, provider status, snapshot path, and run history.
9. Sleep until the next configured interval.

## Provider Registry Contract
Every provider adapter implements:
- `provider_id`
- `display_name`
- `supports_live_sync`
- `is_connected()`
- `fetch_delta(cursor, since_ts)`
- `build_snapshot(records, previous_snapshot)`
- `write_markdown(snapshot, path)` via shared storage
- `project_to_graph(snapshot, tree/dao)` via shared graph projector

V1 provider registry:
- `github`
- `google_workspace`
- `notion`
- `slack`
- `jira`

Live in v1:
- `github`
- `google_workspace`
- `notion`
- `jira`

Placeholders in v1:
- `slack`

## Storage Contract
Markdown is the canonical long-term store.
- Root path: `<covalent_data_dir>/long_term_context/`
- Files: `github.md`, `google_workspace.md`, `notion.md`, `slack.md`, `jira.md`

The graph is a selective projection.
- The graph is optimized for fast lookup and retrieval.
- Markdown keeps richer provider-specific detail and full structured summaries.
- The graph only receives stable, active, referenceable entities with short summaries.

The database persists:
- global sync config
- per-provider cursors and last status
- sync run history

## Graph Vs Markdown Rules
Write to the graph when the item is:
- active
- addressable by a stable external ID
- useful as retrieval context on its own
- brief enough to store as a compact identity/summary record

Keep only in markdown when the item is:
- verbose
- weakly structured
- not stable enough to become a graph node
- better represented as provider-native detail

V1 graph projection rules:
- no direct writes into the existing product/task graph
- all sync writes stay inside the `Long Term Context` subtree
- entity nodes are upserted by stable external ID
- raw message bodies, full docs, and long threads do not go into the graph

## Shared Markdown Shape
Every provider file uses the same top-level structure:
- `# <Provider> Context Snapshot`
- `## Sync Metadata`
- `## Containers`
- `## Active Entities`
- `## Relevant People`
- `## Cross-Links`
- `## Open Questions / Watch Items`

Every entity block uses this fixed field order:
- `entity_type`
- `external_id`
- `title`
- `status`
- `summary`
- `project`
- `feature_tags`
- `people`
- `related_entities`
- `updated_at`
- `source_url`

Provider-specific fields are appended after the shared fields.

## Per-Integration Schemas

### GitHub
Containers:
- organization/user
- repository

Active entities:
- `pull_request`
  - `repo`
  - `number`
  - `author`
  - `reviewers`
  - `labels`
  - `base_branch`
  - `head_branch`
  - `linked_issue_ids`
- `issue`
  - `repo`
  - `number`
  - `assignees`
  - `labels`
  - `milestone`
  - `linked_pr_ids`

People:
- GitHub handles touching repos/issues/PRs

Cross-links:
- GitHub entity -> Jira ticket
- GitHub entity -> Slack thread
- GitHub entity -> Notion or Google doc

### Jira
Containers:
- site
- project

Active entities:
- `ticket`
  - `ticket_key`
  - `issue_type`
  - `priority`
  - `assignee`
  - `reporter`
  - `sprint`
  - `epic`
  - `linked_github_ids`
  - `linked_slack_ids`

People:
- assignee
- reporter
- mentioned collaborators

Cross-links:
- ticket -> PR/issue/thread/doc

### Slack
Containers:
- workspace
- channel

Active entities:
- `thread`
  - `channel`
  - `thread_ts`
  - `participants`
  - `latest_message_at`
  - `unresolved_asks`
  - `linked_github_ids`
  - `linked_jira_ids`

People:
- participants with recent involvement and referenced projects/features

Cross-links:
- thread -> Jira/GitHub/doc/email

### Notion
Containers:
- workspace
- parent page/database

Active entities:
- `page`
  - `page_id`
  - `owner`
  - `last_editor`
  - `database`
  - `status_field`
  - `linked_github_ids`
  - `linked_jira_ids`
- `database_item`
  - `page_id`
  - `owner`
  - `last_editor`
  - `database`
  - `status_field`
  - `linked_github_ids`
  - `linked_jira_ids`

People:
- owners
- editors

Cross-links:
- page/item -> tickets/PRs/threads/docs

### Google Workspace
Single provider/file for now:
- `google_workspace`
- `google_workspace.md`
- active slices run every sync, with broader bootstrap backfills on the first 3 successful runs

Containers:
- account
- shared drive/folder/mailbox/calendar

Active entities:
- `email_thread`
  - `thread_id`
  - `subject`
  - `participants`
  - `last_message_at`
  - `labels`
  - `linked_entities`
- `drive_file`
  - `file_id`
  - `mime_type`
  - `owner`
  - `folder_path`
  - `last_modified_by`
- `doc`
  - `file_id`
  - `mime_type`
  - `owner`
  - `folder_path`
  - `last_modified_by`
  - `doc_type`
- `calendar_event`
  - `event_id`
  - `start_at`
  - `end_at`
  - `attendees`
  - `meeting_project`

People:
- email participants
- doc owners/editors
- recurring meeting attendees

Cross-links:
- email/doc/event -> GitHub/Jira/Slack/Notion entities

Heuristic sync policy:
- every run syncs recent inbox threads, recently modified Drive/Docs artifacts, and near-future calendar events
- the first 3 successful runs also include broader Gmail/Drive/Calendar backfills so the local graph can learn the user's org context early

## Graph Projection Schema
Reuse the existing root node and create or upsert:
- `Long Term Context`

Under it:
- `GitHub`
- `Google Workspace`
- `Notion`
- `Slack`
- `Jira`

Under each provider node:
- repository/project/channel/workspace/folder/calendar containers as needed

Under each container node:
- active entity nodes only

Entity node metadata:
- `[provider/entity_type] stable_external_id - short title`

Entity node data categories:
- `large_context_identity`
  - `provider`
  - `entity_type`
  - `external_id`
  - `container_id`
- `large_context_summary`
  - `title`
  - `summary`
  - `status`
  - `project`
  - `feature_tags_json`
  - `updated_at`
  - `source_url`
- `large_context_people`
  - `people_json`
- `large_context_links`
  - `related_entities_json`
- `large_context_sync`
  - `snapshot_file`
  - `last_synced_at`
  - `run_id`

## Placeholder Policy
Slack and Jira are part of the registry now so engineers can implement in parallel, but in v1 this pass only ships:
- explicit markdown schema contracts
- explicit graph projection contracts
- API visibility through provider/status endpoints
- runtime status `not_supported_yet`

They do not fetch live data or write live graph data yet.

## Failure Handling And Idempotency
- Provider failures do not abort the whole run.
- Every provider state is persisted independently.
- Run history records partial success vs full error.
- Markdown writes are atomic via temp-file replace.
- Graph projection upserts entity nodes by provider/entity/external ID.
- Stale provider-owned entity nodes are removed from that provider subtree if they are no longer present in the current snapshot.

## Rollout Notes
- V1 uses one global interval, default `60`, minimum `30`.
- Scheduler lives in FastAPI and the frontend only edits config or triggers manual runs.
- Graph projection is intentionally conservative to preserve retrieval quality.
- Future phases can add deeper auto-linking into the main task graph once the long-term schemas are stable.
