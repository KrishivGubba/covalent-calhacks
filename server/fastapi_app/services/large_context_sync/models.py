"""Pydantic models for the large context sync subsystem."""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class LargeContextSyncConfig(BaseModel):
    enabled: bool = True
    interval_minutes: int = Field(default=60, ge=30)
    projection_mode: str = "provider_subtree"
    markdown_root: str
    last_scheduler_heartbeat: Optional[str] = None


class LargeContextProviderState(BaseModel):
    provider: str
    supports_live_sync: bool
    cursor_json: Optional[Dict[str, Any]] = None
    last_started_at: Optional[str] = None
    last_completed_at: Optional[str] = None
    last_success_at: Optional[str] = None
    last_error: Optional[str] = None
    status: str = "idle"
    last_snapshot_path: Optional[str] = None


class LargeContextRunSummary(BaseModel):
    run_id: str
    started_at: str
    completed_at: Optional[str] = None
    status: str = "running"
    providers_attempted: List[str] = Field(default_factory=list)
    providers_succeeded: List[str] = Field(default_factory=list)
    providers_failed: List[str] = Field(default_factory=list)
    error_json: Optional[Dict[str, Any]] = None


class ProviderRegistryInfo(BaseModel):
    provider_id: str
    display_name: str
    supports_live_sync: bool
    file_name: str
    integration_provider_key: Optional[str] = None


class ProviderFetchResult(BaseModel):
    records: List[Dict[str, Any]] = Field(default_factory=list)
    next_cursor: Optional[Dict[str, Any]] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class SnapshotContainer(BaseModel):
    container_type: str
    container_id: str
    title: str
    summary: Optional[str] = None
    parent_id: Optional[str] = None
    source_url: Optional[str] = None


class SnapshotEntity(BaseModel):
    entity_type: str
    external_id: str
    title: str
    status: str
    summary: str
    project: Optional[str] = None
    feature_tags: List[str] = Field(default_factory=list)
    people: List[str] = Field(default_factory=list)
    related_entities: List[str] = Field(default_factory=list)
    updated_at: Optional[str] = None
    source_url: Optional[str] = None
    container_id: str
    extra_fields: Dict[str, Any] = Field(default_factory=dict)


class SnapshotPerson(BaseModel):
    identifier: str
    display_name: str
    role: Optional[str] = None
    related_entities: List[str] = Field(default_factory=list)


class SnapshotCrossLink(BaseModel):
    source_entity_id: str
    target_entity_id: str
    relationship: str
    note: Optional[str] = None


class ProviderSnapshot(BaseModel):
    provider_id: str
    provider_display_name: str
    generated_at: str
    cursor: Optional[Dict[str, Any]] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    containers: List[SnapshotContainer] = Field(default_factory=list)
    entities: List[SnapshotEntity] = Field(default_factory=list)
    relevant_people: List[SnapshotPerson] = Field(default_factory=list)
    cross_links: List[SnapshotCrossLink] = Field(default_factory=list)
    open_questions: List[str] = Field(default_factory=list)
    watch_items: List[str] = Field(default_factory=list)


ManualRunMode = Literal["all_connected_live", "providers", "integrations"]


class ManualRunRequest(BaseModel):
    mode: Optional[ManualRunMode] = None
    provider_ids: List[str] = Field(default_factory=list)
    integration_ids: List[str] = Field(default_factory=list)
    providers: Optional[List[str]] = None


class LargeContextSyncConfigUpdate(BaseModel):
    enabled: bool
    interval_minutes: int = Field(ge=30)
