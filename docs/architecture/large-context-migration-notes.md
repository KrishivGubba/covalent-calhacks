# Large Context Migration Notes

## Purpose
This note explains how existing and future integrations should move from the old full-snapshot mindset to the new entity-state comparison model.

## Existing Providers
### GitHub
Current GitHub sync can migrate cleanly because its entities already have stable IDs.

Migration target:
- keep repository/issue/PR containers
- treat issues and PRs as touched entities
- compare by normalized issue/PR state
- only rewrite changed issues/PRs

### Notion
Notion needs stronger entity granularity decisions.

Recommended pattern:
- `page`
- `database_item`

Be careful with:
- very large database scans
- pages whose title is weak but page ID is stable
- property normalization order

### Jira
Jira should be straightforward.

Recommended pattern:
- one durable entity per issue key
- optional future entities for sprints/epics if they become retrieval-critical

Urgency signals:
- priority
- assignee / reporter changes
- stale ticket movement

### Slack
Slack should be built directly on the new model, not retrofitted from markdown-first behavior.

Recommended entity granularity:
- thread as the primary durable entity
- channel as a container only

Stable ID:
- `channel_id + thread_ts`

Urgency signals:
- unresolved asks
- unanswered mentions
- decision-making threads tied to active work

## Choosing Entity Granularity
A provider should pick the smallest unit that is:
- stable
- retrievable on its own
- likely to appear in user workflow again

Good examples:
- email thread
- drive document
- GitHub PR
- Jira ticket
- Notion page
- Slack thread

Avoid overly broad entities:
- an entire mailbox
- an entire workspace
- an entire database
- an entire repo when issue/PR granularity is what matters

## What Makes a Good External ID
A good external ID:
- comes from the upstream system
- survives title or status changes
- does not depend on local storage
- is unique within the provider

If an upstream object does not have a stable ID, build one from immutable components only.

## Provider Heuristics vs Shared Correlation
Put provider-specific urgency in the provider/engine-facing entity content:
- unread
- priority
- soon
- unresolved
- linked work refs

Keep shared logic in the engine:
- fingerprint comparison
- changed/freshness scoring
- active TTL
- query-time ranking

## Migration Rule of Thumb
If an integration currently says:
- “rebuild the whole snapshot”

it should become:
- “fetch touched entities”
- “compare fingerprint to stored state”
- “rewrite only changed graph nodes”
- “promote only active entities”
