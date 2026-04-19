from __future__ import annotations

import importlib
import sys
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.append(str(ROOT / "context-engine"))

from init_db import create_schema, ensure_parent_dir


class FakeResponse:
    def __init__(self, payload: dict, ok: bool = True, status_code: int = 200):
        self._payload = payload
        self.ok = ok
        self.status_code = status_code
        self.text = str(payload)

    def json(self):
        return self._payload


def _prepare_db(db_path: Path) -> None:
    from server.fastapi_app.dependencies import get_encrypted_conn

    ensure_parent_dir(str(db_path))
    with get_encrypted_conn(str(db_path)) as conn:
        create_schema(conn)
        conn.commit()


def _make_app(tmp_path: Path, monkeypatch):
    db_path = tmp_path / "graph.db"
    data_dir = tmp_path / "data"

    monkeypatch.setenv("GRAPH_DB_PATH", str(db_path))
    monkeypatch.setenv("COVALENT_DATA_DIR", str(data_dir))
    monkeypatch.setenv("MOUNT_MCP_SERVER", "false")
    monkeypatch.setenv("JIRA_CLIENT_ID", "jira-client-id")
    monkeypatch.setenv("JIRA_CLIENT_SECRET", "jira-client-secret")

    import security.key_manager as key_manager

    monkeypatch.setattr(key_manager, "get_db_encryption_key", lambda: "0" * 64)
    for module_name in ["graph_dao", "server.integration_dao", "server.auth_dao"]:
        try:
            module = importlib.import_module(module_name)
        except Exception:
            continue
        if hasattr(module, "get_db_encryption_key"):
            monkeypatch.setattr(module, "get_db_encryption_key", lambda: "0" * 64)

    import server.fastapi_app.dependencies as dependencies
    import covalent_mcp.toolclasses.jira.auth as jira_auth

    importlib.reload(jira_auth)
    importlib.reload(dependencies)
    dependencies.reset_cached_dependencies()
    _prepare_db(db_path)

    import server.fastapi_app.main as main

    importlib.reload(main)
    dependencies.reset_cached_dependencies()
    app = main.create_app(large_context_provider_registry=[])
    return app, dependencies.get_integration_dao(), dependencies.get_auth_dao()


def test_jira_oauth_callback_persists_connection_and_requires_configuration(tmp_path, monkeypatch):
    app, _, _ = _make_app(tmp_path, monkeypatch)

    def fake_post(url, json=None, headers=None, timeout=None):  # noqa: A002
        assert url.endswith("/integrations/jira/exchange")
        return FakeResponse(
            {
                "access_token": "jira-access",
                "refresh_token": "jira-refresh",
                "expires_in": 3600,
                "scope": "offline_access read:jira-work write:jira-work",
                "accessible_resources": [
                    {
                        "id": "cloud-1",
                        "name": "Acme Jira",
                        "url": "https://acme.atlassian.net",
                        "scopes": ["read:jira-work"],
                    }
                ],
                "account_id": "acct-1",
                "email": "jira@example.com",
                "display_name": "Jira User",
            }
        )

    import server.fastapi_app.routers.integrations as integrations_router

    monkeypatch.setattr(integrations_router.http_requests, "post", fake_post)

    with TestClient(app) as client:
        start = client.post(
            "/integrations/jira/start",
            json={"state": "jira-state", "auth_token": "auth-jwt"},
        )
        assert start.status_code == 200

        callback = client.get("/integrations/jira/callback?code=oauth-code&state=jira-state")
        assert callback.status_code == 200

        status = client.get("/integrations/status")
        assert status.status_code == 200
        jira_status = next(item for item in status.json()["integrations"] if item["id"] == "jira")
        assert jira_status["connected"] is True
        assert jira_status["configured"] is False
        assert jira_status["needs_configuration"] is True
        assert jira_status["configuration"]["accessible_resources"][0]["cloud_id"] == "cloud-1"


def test_jira_oauth_callback_falls_back_to_direct_exchange_when_lambda_is_outdated(tmp_path, monkeypatch):
    app, integration_dao, _ = _make_app(tmp_path, monkeypatch)

    import covalent_mcp.toolclasses.jira.auth as jira_auth

    def fake_post(url, json=None, headers=None, timeout=None):  # noqa: A002
        if url.endswith("/integrations/jira/exchange"):
            return FakeResponse(
                {
                    "error": "validation_error",
                    "error_description": "messages field is required and must be a list",
                },
                ok=False,
                status_code=400,
            )
        if url == "https://auth.atlassian.com/oauth/token":
            return FakeResponse(
                {
                    "access_token": "jira-access",
                    "refresh_token": "jira-refresh",
                    "expires_in": 3600,
                    "scope": "offline_access read:jira-work write:jira-work",
                    "token_type": "Bearer",
                }
            )
        raise AssertionError(f"Unexpected POST URL: {url}")

    def fake_get(url, headers=None, timeout=None):
        if url == "https://api.atlassian.com/oauth/token/accessible-resources":
            return FakeResponse(
                [
                    {
                        "id": "cloud-1",
                        "name": "Acme Jira",
                        "url": "https://acme.atlassian.net",
                        "scopes": ["read:jira-work"],
                    }
                ]
            )
        if url == "https://api.atlassian.com/me":
            return FakeResponse(
                {
                    "account_id": "acct-1",
                    "email": "jira@example.com",
                    "name": "Jira User",
                }
            )
        raise AssertionError(f"Unexpected GET URL: {url}")

    monkeypatch.setattr(jira_auth.http_requests, "post", fake_post)
    monkeypatch.setattr(jira_auth.http_requests, "get", fake_get)

    with TestClient(app) as client:
        start = client.post(
            "/integrations/jira/start",
            json={"state": "jira-state", "auth_token": "auth-jwt"},
        )
        assert start.status_code == 200

        callback = client.get("/integrations/jira/callback?code=oauth-code&state=jira-state")
        assert callback.status_code == 200

    token_data = integration_dao.get_token("jira")
    assert token_data is not None
    assert token_data["access_token"] == "jira-access"
    assert token_data["refresh_token"] == "jira-refresh"


def test_jira_configuration_round_trip_and_project_listing(tmp_path, monkeypatch):
    app, integration_dao, _ = _make_app(tmp_path, monkeypatch)
    integration_dao.save_token(
        provider="jira",
        access_token="jira-access",
        refresh_token="jira-refresh",
        expires_at=None,
        scopes="offline_access read:jira-work write:jira-work",
        provider_metadata={
            "accessible_resources": [
                {
                    "cloud_id": "cloud-1",
                    "site_name": "Acme Jira",
                    "site_url": "https://acme.atlassian.net",
                }
            ],
            "project_keys": [],
            "project_names_by_key": {},
        },
    )

    import server.fastapi_app.routers.integrations as integrations_router

    monkeypatch.setattr(
        integrations_router.JiraClient,
        "get_accessible_resources",
        lambda self: [  # noqa: ARG005
            {
                "id": "cloud-1",
                "name": "Acme Jira",
                "url": "https://acme.atlassian.net",
                "scopes": ["read:jira-work"],
            }
        ],
    )
    monkeypatch.setattr(
        integrations_router.JiraClient,
        "list_projects",
        lambda self: [  # noqa: ARG005
            {"id": "100", "key": "PROJ", "name": "Project Atlas", "projectTypeKey": "software"},
            {"id": "101", "key": "OPS", "name": "Operations", "projectTypeKey": "service_desk"},
        ],
    )

    with TestClient(app) as client:
        config = client.get("/integrations/jira/config")
        assert config.status_code == 200
        assert config.json()["config"]["accessible_resources"][0]["cloud_id"] == "cloud-1"

        projects = client.get("/integrations/jira/projects?cloud_id=cloud-1")
        assert projects.status_code == 200
        assert len(projects.json()["projects"]) == 2

        update = client.put(
            "/integrations/jira/config",
            json={"cloud_id": "cloud-1", "project_keys": ["PROJ", "OPS"]},
        )
        assert update.status_code == 200
        assert update.json()["configured"] is True

        status = client.get("/integrations/status")
        jira_status = next(item for item in status.json()["integrations"] if item["id"] == "jira")
        assert jira_status["configured"] is True
        assert jira_status["configuration"]["project_count"] == 2


def test_jira_refresh_endpoint_updates_saved_token(tmp_path, monkeypatch):
    app, integration_dao, auth_dao = _make_app(tmp_path, monkeypatch)
    integration_dao.save_token(
        provider="jira",
        access_token="old-access",
        refresh_token="jira-refresh",
        expires_at=None,
        scopes="offline_access",
        provider_metadata={"accessible_resources": [], "project_keys": [], "project_names_by_key": {}},
    )
    auth_dao.save_session(user_id="user-1", access_token="auth-jwt")

    def fake_post(url, json=None, headers=None, timeout=None):  # noqa: A002
        assert url.endswith("/integrations/jira/refresh")
        return FakeResponse(
            {
                "access_token": "new-access",
                "refresh_token": "new-refresh",
                "expires_in": 7200,
            }
        )

    import server.fastapi_app.routers.integrations as integrations_router

    monkeypatch.setattr(integrations_router.http_requests, "post", fake_post)

    with TestClient(app) as client:
        refresh = client.post("/integrations/jira/refresh", json={})
        assert refresh.status_code == 200
        assert refresh.json()["access_token"] == "new-access"

    token_data = integration_dao.get_token("jira")
    assert token_data["access_token"] == "new-access"
    assert token_data["refresh_token"] == "new-refresh"


def test_jira_refresh_helper_falls_back_to_direct_refresh(tmp_path, monkeypatch):
    _, integration_dao, _ = _make_app(tmp_path, monkeypatch)
    integration_dao.save_token(
        provider="jira",
        access_token="old-access",
        refresh_token="jira-refresh",
        expires_at=None,
        scopes="offline_access",
        provider_metadata={"accessible_resources": [], "project_keys": [], "project_names_by_key": {}},
    )

    import covalent_mcp.toolclasses.jira.auth as jira_auth

    def fake_post(url, json=None, headers=None, timeout=None):  # noqa: A002
        if url.endswith("/integrations/jira/refresh"):
            return FakeResponse(
                {
                    "error": "validation_error",
                    "error_description": "messages field is required and must be a list",
                },
                ok=False,
                status_code=400,
            )
        if url == "https://auth.atlassian.com/oauth/token":
            return FakeResponse(
                {
                    "access_token": "new-access",
                    "refresh_token": "new-refresh",
                    "expires_in": 7200,
                }
            )
        raise AssertionError(f"Unexpected POST URL: {url}")

    monkeypatch.setattr(jira_auth, "get_auth0_jwt", lambda _db_path: "auth-jwt")
    monkeypatch.setattr(jira_auth.http_requests, "post", fake_post)

    refreshed = jira_auth.refresh_jira_token_via_lambda(integration_dao)
    assert refreshed["access_token"] == "new-access"

    token_data = integration_dao.get_token("jira")
    assert token_data["access_token"] == "new-access"
    assert token_data["refresh_token"] == "new-refresh"
