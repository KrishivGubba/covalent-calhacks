from __future__ import annotations

import importlib
import sys
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.append(str(ROOT / "context-engine"))

from init_db import create_schema, ensure_parent_dir  # noqa: E402


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
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "google-client-id")

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

    importlib.reload(dependencies)
    dependencies.reset_cached_dependencies()
    _prepare_db(db_path)

    import server.fastapi_app.main as main

    importlib.reload(main)
    dependencies.reset_cached_dependencies()
    app = main.create_app(large_context_provider_registry=[])
    return app, dependencies.get_integration_dao()


def test_google_oauth_callback_persists_docs_scope_and_updated_status_text(tmp_path, monkeypatch):
    app, integration_dao = _make_app(tmp_path, monkeypatch)

    import server.fastapi_app.routers.integrations as integrations_router

    docs_scope = "https://www.googleapis.com/auth/documents"
    assert docs_scope in integrations_router.GOOGLE_SCOPES

    def fake_post(url, json=None, headers=None, timeout=None):  # noqa: A002, ARG001
        assert url.endswith("/integrations/google/exchange")
        return FakeResponse(
            {
                "access_token": "google-access",
                "refresh_token": "google-refresh",
                "expires_in": 3600,
                "scope": integrations_router.GOOGLE_SCOPES,
            }
        )

    def fake_get(url, headers=None, timeout=None):  # noqa: ARG001
        assert url == "https://www.googleapis.com/oauth2/v2/userinfo"
        return FakeResponse({"email": "user@acme.com"})

    monkeypatch.setattr(integrations_router.http_requests, "post", fake_post)
    monkeypatch.setattr(integrations_router.http_requests, "get", fake_get)

    with TestClient(app) as client:
        start = client.post(
            "/integrations/google/start",
            json={"state": "google-state", "code_verifier": "verifier", "auth_token": "auth-jwt"},
        )
        assert start.status_code == 200

        callback = client.get("/integrations/google/callback?code=oauth-code&state=google-state")
        assert callback.status_code == 200

        status = client.get("/integrations/status")
        assert status.status_code == 200
        google_status = next(item for item in status.json()["integrations"] if item["id"] == "google")
        assert google_status["connected"] is True
        assert google_status["description"] == "Docs, Drive, Mail, Calendar"

    token_data = integration_dao.get_token("google")
    assert token_data is not None
    assert docs_scope in (token_data["scopes"] or "")
    assert token_data["provider_metadata"]["email"] == "user@acme.com"
