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
JIRA_CLIENT_ID = os.getenv("JIRA_CLIENT_ID", "")
JIRA_CLIENT_SECRET = os.getenv("JIRA_CLIENT_SECRET", "")


def _get_error_fields(payload: Dict[str, Any], fallback: str) -> Tuple[str, str]:
    error = payload.get("error") or fallback
    error_description = (
        payload.get("error_description")
        or payload.get("message")
        or payload.get("detail")
        or fallback
    )
    return str(error), str(error_description)


def _decode_json_response(response) -> Dict[str, Any]:
    try:
        return response.json()
    except ValueError:
        return {}


def _fetch_jira_accessible_resources(access_token: str) -> list[Dict[str, Any]]:
    response = http_requests.get(
        "https://api.atlassian.com/oauth/token/accessible-resources",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
        },
        timeout=15,
    )
    payload = _decode_json_response(response)
    if not response.ok:
        _, error_description = _get_error_fields(payload, response.text or "Could not fetch Jira sites")
        raise RuntimeError(error_description)
    if isinstance(payload, list):
        return payload
    raise RuntimeError("Unexpected Jira accessible resources response")


def _fetch_jira_identity(access_token: str) -> Dict[str, Any]:
    response = http_requests.get(
        "https://api.atlassian.com/me",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
        },
        timeout=15,
    )
    payload = _decode_json_response(response)
    if not response.ok:
        _, error_description = _get_error_fields(payload, response.text or "Could not fetch Jira identity")
        raise RuntimeError(error_description)
    return payload


def exchange_jira_code_direct(code: str, redirect_uri: str) -> Dict[str, Any]:
    if not JIRA_CLIENT_ID or not JIRA_CLIENT_SECRET:
        raise RuntimeError("Jira OAuth not configured on server")

    response = http_requests.post(
        "https://auth.atlassian.com/oauth/token",
        json={
            "grant_type": "authorization_code",
            "client_id": JIRA_CLIENT_ID,
            "client_secret": JIRA_CLIENT_SECRET,
            "code": code,
            "redirect_uri": redirect_uri,
        },
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        timeout=15,
    )
    payload = _decode_json_response(response)
    if not response.ok or "error" in payload:
        _, error_description = _get_error_fields(payload, response.text or "Token exchange failed")
        raise RuntimeError(error_description)

    access_token = payload.get("access_token")
    if not access_token:
        raise RuntimeError("Token exchange failed")

    resources = _fetch_jira_accessible_resources(access_token)
    identity: Dict[str, Any] = {}
    try:
        identity = _fetch_jira_identity(access_token)
    except Exception as exc:
        log.warning(f"Could not fetch Jira identity during direct exchange: {exc}")

    return {
        "access_token": access_token,
        "refresh_token": payload.get("refresh_token"),
        "expires_in": payload.get("expires_in"),
        "scope": payload.get("scope"),
        "token_type": payload.get("token_type"),
        "accessible_resources": resources,
        "account_id": identity.get("account_id") or identity.get("accountId"),
        "email": identity.get("email"),
        "display_name": identity.get("name") or identity.get("displayName"),
    }


def refresh_jira_token_direct(refresh_token: str) -> Dict[str, Any]:
    if not JIRA_CLIENT_ID or not JIRA_CLIENT_SECRET:
        raise RuntimeError("Jira OAuth not configured on server")

    response = http_requests.post(
        "https://auth.atlassian.com/oauth/token",
        json={
            "grant_type": "refresh_token",
            "client_id": JIRA_CLIENT_ID,
            "client_secret": JIRA_CLIENT_SECRET,
            "refresh_token": refresh_token,
        },
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        timeout=15,
    )
    payload = _decode_json_response(response)
    if not response.ok or "error" in payload:
        _, error_description = _get_error_fields(payload, response.text or "Jira token refresh failed")
        raise RuntimeError(error_description)
    return payload


def exchange_jira_code(auth_jwt: Optional[str], code: str, redirect_uri: str) -> Dict[str, Any]:
    lambda_error: Optional[RuntimeError] = None
    if auth_jwt:
        response = http_requests.post(
            f"{LAMBDA_GATEWAY_URL}/integrations/jira/exchange",
            json={
                "code": code,
                "redirect_uri": redirect_uri,
            },
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {auth_jwt}",
            },
            timeout=15,
        )
        payload = _decode_json_response(response)
        if response.ok and "error" not in payload:
            return payload

        err, err_desc = _get_error_fields(payload, response.text or "Token exchange failed")
        lambda_error = RuntimeError(f"{err} - {err_desc}")
        if JIRA_CLIENT_ID and JIRA_CLIENT_SECRET:
            log.warning(f"Jira token exchange via Lambda failed, falling back to direct exchange: {lambda_error}")
        else:
            raise lambda_error

    if JIRA_CLIENT_ID and JIRA_CLIENT_SECRET:
        return exchange_jira_code_direct(code, redirect_uri)

    if lambda_error is not None:
        raise lambda_error
    raise RuntimeError("Jira OAuth not configured on server")


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

    lambda_error: Optional[RuntimeError] = None
    response = http_requests.post(
        f"{LAMBDA_GATEWAY_URL}/integrations/jira/refresh",
        json={"refresh_token": refresh_token},
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {auth_jwt}",
        },
        timeout=15,
    )
    result = _decode_json_response(response)
    if not response.ok or "error" in result:
        err, err_desc = _get_error_fields(result, response.text or "Jira token refresh failed")
        lambda_error = RuntimeError(f"Jira token refresh failed: {err} - {err_desc}")
        if JIRA_CLIENT_ID and JIRA_CLIENT_SECRET:
            log.warning(f"Jira token refresh via Lambda failed, falling back to direct refresh: {lambda_error}")
            result = refresh_jira_token_direct(refresh_token)
        else:
            raise lambda_error

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
