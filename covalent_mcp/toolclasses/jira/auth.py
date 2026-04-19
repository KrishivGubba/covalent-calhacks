"""Jira connection and token helpers."""

from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta
from typing import Any, Dict, Optional, Tuple

import requests as http_requests

from covalent_mcp.toolclasses.issue_tracker.common import (
    DB_PATH,
    get_auth0_jwt,
    get_integration_dao,
    is_token_expired,
)


PROJECT_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)
sys.path.insert(0, PROJECT_ROOT)

from logger import get_logger

log = get_logger()

LAMBDA_GATEWAY_URL = os.getenv(
    "LAMBDA_GATEWAY_URL",
    "https://gtfrn4otol.execute-api.us-east-1.amazonaws.com",
)


def refresh_jira_token_via_lambda(integration_dao=None) -> Dict[str, Any]:
    dao = integration_dao or get_integration_dao(DB_PATH)
    token_data = dao.get_token("jira")
    if not token_data:
        raise RuntimeError("Jira not connected. Please authenticate Jira first.")

    refresh_token = token_data.get("refresh_token")
    if not refresh_token:
        raise RuntimeError("No Jira refresh token available. Disconnect and reconnect Jira.")

    auth_jwt = get_auth0_jwt(DB_PATH)
    if not auth_jwt:
        raise RuntimeError("No active Auth0 session found. Please log in first.")

    response = http_requests.post(
        f"{LAMBDA_GATEWAY_URL}/integrations/jira/refresh",
        json={"refresh_token": refresh_token},
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {auth_jwt}",
        },
        timeout=15,
    )
    result = response.json()
    if not response.ok or "error" in result:
        err = result.get("error", "refresh_failed")
        err_desc = result.get("error_description", "Jira token refresh failed")
        raise RuntimeError(f"Jira token refresh failed: {err} - {err_desc}")

    new_access_token = result.get("access_token")
    expires_in = result.get("expires_in", 3600)
    expires_at = (datetime.utcnow() + timedelta(seconds=expires_in)).isoformat()
    new_refresh_token = result.get("refresh_token") or refresh_token

    dao.save_token(
        provider="jira",
        access_token=new_access_token,
        refresh_token=new_refresh_token,
        expires_at=expires_at,
        scopes=token_data.get("scopes"),
        provider_metadata=token_data.get("provider_metadata"),
    )
    log.info("Jira access token refreshed successfully")
    return {
        "access_token": new_access_token,
        "refresh_token": new_refresh_token,
        "expires_at": expires_at,
    }


def get_jira_token_data(integration_dao=None) -> Optional[Dict[str, Any]]:
    dao = integration_dao or get_integration_dao(DB_PATH)
    token_data = dao.get_token("jira")
    if not token_data:
        return None
    if is_token_expired(token_data.get("expires_at")):
        try:
            refresh_jira_token_via_lambda(dao)
            token_data = dao.get_token("jira")
        except Exception as exc:
            log.warning(f"Jira token refresh failed: {exc}")
    return token_data


def get_jira_connection(integration_dao=None, *, require_configured: bool = False) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    token_data = get_jira_token_data(integration_dao)
    if not token_data or not token_data.get("access_token"):
        raise RuntimeError("Jira is not connected. Please connect Jira from the Integrations page.")

    metadata = dict(token_data.get("provider_metadata") or {})
    cloud_id = metadata.get("cloud_id") or metadata.get("site_id")
    project_keys = metadata.get("project_keys") or []
    if require_configured and (not cloud_id or not project_keys):
        raise RuntimeError(
            "Jira is connected but not configured. Select a Jira site and at least one project first."
        )
    return token_data, metadata
