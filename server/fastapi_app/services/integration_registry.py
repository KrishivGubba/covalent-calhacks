"""Shared integration provider registry and status helpers."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Literal, Optional


AuthKind = Literal["oauth", "local", "included"]


@dataclass(frozen=True)
class IntegrationProviderConfig:
    provider_id: str
    name: str
    description: str
    icon: str
    auth_kind: AuthKind
    included: bool = False
    required_onboarding: bool = False
    configurable: bool = False


PROVIDER_CONFIGS: Dict[str, IntegrationProviderConfig] = {
    "filesystem": IntegrationProviderConfig(
        provider_id="filesystem",
        name="Filesystem",
        description="Access local files and directories",
        icon="📁",
        auth_kind="local",
        required_onboarding=True,
    ),
    "github": IntegrationProviderConfig(
        provider_id="github",
        name="GitHub",
        description="Access repositories, issues, and pull requests",
        icon="🐙",
        auth_kind="oauth",
        required_onboarding=True,
    ),
    "perplexity": IntegrationProviderConfig(
        provider_id="perplexity",
        name="Perplexity Search",
        description="AI-powered web search",
        icon="🔍",
        auth_kind="included",
        included=True,
    ),
    "notion": IntegrationProviderConfig(
        provider_id="notion",
        name="Notion",
        description="Access Notion workspaces and pages",
        icon="📝",
        auth_kind="oauth",
        required_onboarding=True,
    ),
    "google": IntegrationProviderConfig(
        provider_id="google",
        name="Google Workspace",
        description="Docs, Drive, Mail, Calendar",
        icon="🔷",
        auth_kind="oauth",
        required_onboarding=True,
    ),
    "jira": IntegrationProviderConfig(
        provider_id="jira",
        name="Jira",
        description="Access Jira projects, tickets, and workflows",
        icon="🎫",
        auth_kind="oauth",
        configurable=True,
    ),
    "slack": IntegrationProviderConfig(
        provider_id="slack",
        name="Slack",
        description="Read Slack DMs and channels you have access to",
        icon="💬",
        auth_kind="oauth",
        required_onboarding=True,
    ),
}


def get_provider_configs() -> List[IntegrationProviderConfig]:
    return list(PROVIDER_CONFIGS.values())


def get_provider_config(provider_id: str) -> IntegrationProviderConfig:
    return PROVIDER_CONFIGS[provider_id]


def is_issue_tracker_metadata_configured(metadata: Dict[str, Any] | None) -> bool:
    metadata = metadata or {}
    cloud_id = metadata.get("cloud_id") or metadata.get("site_id")
    project_keys = metadata.get("project_keys") or []
    return bool(cloud_id and project_keys)


def build_filesystem_description(integration_dao) -> str:
    root = integration_dao.get_filesystem_root()
    if root:
        display_path = root
        if len(display_path) > 50:
            display_path = "..." + display_path[-47:]
        return f"Access local files and directories ({display_path})"
    return PROVIDER_CONFIGS["filesystem"].description


def build_integration_statuses(integration_dao) -> List[Dict[str, Any]]:
    statuses = integration_dao.get_all_statuses()
    results: List[Dict[str, Any]] = []

    for config in get_provider_configs():
        if config.included:
            results.append(
                {
                    "id": config.provider_id,
                    "name": config.name,
                    "description": config.description,
                    "icon": config.icon,
                    "auth_kind": config.auth_kind,
                    "included": config.included,
                    "required_onboarding": config.required_onboarding,
                    "configurable": config.configurable,
                    "connected": True,
                    "configured": True,
                    "needs_configuration": False,
                    "configuration": None,
                }
            )
            continue

        token = integration_dao.get_token(config.provider_id)
        connected = statuses.get(config.provider_id, False)
        description = build_filesystem_description(integration_dao) if config.provider_id == "filesystem" else config.description
        status_payload: Dict[str, Any] = {
            "id": config.provider_id,
            "name": config.name,
            "description": description,
            "icon": config.icon,
            "auth_kind": config.auth_kind,
            "included": config.included,
            "required_onboarding": config.required_onboarding,
            "configurable": config.configurable,
            "connected": connected,
            "configured": connected,
            "needs_configuration": False,
            "configuration": None,
        }

        if config.provider_id == "jira":
            metadata = (token or {}).get("provider_metadata") or {}
            project_keys = metadata.get("project_keys") or []
            configured = connected and is_issue_tracker_metadata_configured(metadata)
            status_payload.update(
                {
                    "configured": configured,
                    "needs_configuration": connected and not configured,
                    "configuration": {
                        "site_id": metadata.get("cloud_id") or metadata.get("site_id"),
                        "site_name": metadata.get("site_name"),
                        "site_url": metadata.get("site_url"),
                        "project_keys": project_keys,
                        "project_count": len(project_keys),
                        "accessible_resources": metadata.get("accessible_resources") or [],
                        "project_names_by_key": metadata.get("project_names_by_key") or {},
                    },
                }
            )

        results.append(status_payload)

    return results
