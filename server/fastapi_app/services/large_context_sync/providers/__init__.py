"""Provider registry for large context sync."""

from __future__ import annotations

from typing import Iterable, List

from server.integration_dao import IntegrationDAO

from .base import LargeContextProvider
from .github import GitHubLargeContextProvider
from .google_workspace import GoogleWorkspaceLargeContextProvider
from .jira import JiraLargeContextProvider
from .notion import NotionLargeContextProvider
from .slack import SlackLargeContextProvider


def build_default_provider_registry(integration_dao: IntegrationDAO) -> List[LargeContextProvider]:
    return [
        GitHubLargeContextProvider(integration_dao),
        GoogleWorkspaceLargeContextProvider(integration_dao),
        NotionLargeContextProvider(),
        SlackLargeContextProvider(integration_dao),
        JiraLargeContextProvider(integration_dao),
    ]


def provider_ids(providers: Iterable[LargeContextProvider]) -> list[str]:
    return [provider.provider_id for provider in providers]
