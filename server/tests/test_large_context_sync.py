from __future__ import annotations

import importlib
import json
import sys
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.append(str(ROOT / "context-engine"))

from init_db import create_schema, ensure_parent_dir
from server.fastapi_app.services.large_context_sync.models import ProviderFetchResult, ProviderSnapshot, SnapshotContainer, SnapshotEntity
from server.fastapi_app.services.large_context_sync.providers.base import LargeContextProvider


class FakeLiveProvider(LargeContextProvider):
    supports_live_sync = True
    file_name = "fake_live.md"
    integration_provider_key = "fake_live"

    def __init__(
        self,
        provider_id: str = "fake_live",
        *,
        connected: bool = True,
        fail: bool = False,
        sleep_seconds: float = 0.0,
        integration_provider_key: str | None = None,
    ):
        self.provider_id = provider_id
        self.display_name = provider_id.replace("_", " ").title()
        self.connected = connected
        self.fail = fail
        self.sleep_seconds = sleep_seconds
        self.integration_provider_key = integration_provider_key or provider_id
        self.received_cursors: list[dict | None] = []
        self.received_since: list[str] = []
        self.calls = 0

    def is_connected(self, integration_dao) -> bool:
        return self.connected

    def fetch_delta(self, cursor, since_ts: str) -> ProviderFetchResult:
        self.received_cursors.append(cursor)
        self.received_since.append(since_ts)
        self.calls += 1
        if self.sleep_seconds:
            time.sleep(self.sleep_seconds)
        if self.fail:
            raise RuntimeError(f"{self.provider_id} exploded")
        return ProviderFetchResult(
            records=[{"title": "Fake Ticket", "summary": "Keep this stable"}],
            next_cursor={"since": f"cursor-{self.calls}"},
            metadata={"source": self.provider_id},
        )

    def build_snapshot(self, fetch_result: ProviderFetchResult, previous_snapshot: ProviderSnapshot | None = None) -> ProviderSnapshot:
        return ProviderSnapshot(
            provider_id=self.provider_id,
            provider_display_name=self.display_name,
            generated_at=f"2026-01-01T00:00:0{self.calls}Z",
            cursor=fetch_result.next_cursor,
            metadata=fetch_result.metadata,
            containers=[SnapshotContainer(container_type="project", container_id=f"{self.provider_id}:project", title=f"{self.display_name} Project")],
            entities=[
                SnapshotEntity(
                    entity_type="ticket",
                    external_id=f"{self.provider_id}:1",
                    title="Fake Ticket",
                    status="open",
                    summary="Keep this stable",
                    project=self.provider_id,
                    feature_tags=["alpha"],
                    people=["person@example.com"],
                    related_entities=[],
                    updated_at="2026-01-01T00:00:00Z",
                    source_url=f"https://example.com/{self.provider_id}/1",
                    container_id=f"{self.provider_id}:project",
                    extra_fields={"ticket_key": "FAKE-1"},
                )
            ],
        )


class FakePlaceholderProvider(LargeContextProvider):
    supports_live_sync = False
    file_name = "slack.md"
    integration_provider_key = "slack"

    def __init__(self, provider_id: str = "slack"):
        self.provider_id = provider_id
        self.display_name = provider_id.title()

    def fetch_delta(self, cursor, since_ts: str) -> ProviderFetchResult:
        return ProviderFetchResult()

    def build_snapshot(self, fetch_result: ProviderFetchResult, previous_snapshot: ProviderSnapshot | None = None) -> ProviderSnapshot:
        raise RuntimeError("placeholder")


def _prepare_db(db_path: Path) -> None:
    from server.fastapi_app.dependencies import get_encrypted_conn

    ensure_parent_dir(str(db_path))
    with get_encrypted_conn(str(db_path)) as conn:
        create_schema(conn)
        conn.commit()


def _make_app(tmp_path: Path, monkeypatch, providers, *, interval_minutes: int | None = None):
    db_path = tmp_path / "graph.db"
    data_dir = tmp_path / "data"

    monkeypatch.setenv("GRAPH_DB_PATH", str(db_path))
    monkeypatch.setenv("COVALENT_DATA_DIR", str(data_dir))
    monkeypatch.setenv("MOUNT_MCP_SERVER", "false")

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

    if interval_minutes is not None:
        with dependencies.get_encrypted_conn(str(db_path)) as conn:
            conn.execute(
                "UPDATE large_context_sync_config SET interval_minutes = ?, enabled = 1 WHERE id = 1",
                (interval_minutes,),
            )
            conn.commit()

    import server.fastapi_app.main as main
    importlib.reload(main)
    dependencies.reset_cached_dependencies()
    app = main.create_app(large_context_provider_registry=providers)
    return app, db_path, data_dir


def _fetch_one(db_path: Path, query: str, params=()):
    from server.fastapi_app.dependencies import get_encrypted_conn

    with get_encrypted_conn(str(db_path)) as conn:
        return conn.execute(query, params).fetchone()


def _fetch_all(db_path: Path, query: str, params=()):
    from server.fastapi_app.dependencies import get_encrypted_conn

    with get_encrypted_conn(str(db_path)) as conn:
        return conn.execute(query, params).fetchall()


def test_scheduler_starts_and_uses_persisted_interval(tmp_path, monkeypatch):
    provider = FakeLiveProvider()
    app, _, _ = _make_app(tmp_path, monkeypatch, [provider], interval_minutes=45)

    with TestClient(app) as client:
        response = client.get("/integrations/large-context-sync/status")
        assert response.status_code == 200
        payload = response.json()
        assert payload["scheduler"]["running"] is True
        assert payload["config"]["interval_minutes"] == 45
        assert payload["scheduler"]["next_run_at"] is not None


def test_put_config_updates_interval_and_disable_state(tmp_path, monkeypatch):
    provider = FakeLiveProvider()
    app, _, _ = _make_app(tmp_path, monkeypatch, [provider])

    with TestClient(app) as client:
        response = client.put("/integrations/large-context-sync/config", json={"enabled": True, "interval_minutes": 30})
        assert response.status_code == 200
        time.sleep(0.1)
        status = client.get("/integrations/large-context-sync/status").json()
        assert status["config"]["interval_minutes"] == 30
        assert status["scheduler"]["next_run_at"] is not None

        response = client.put("/integrations/large-context-sync/config", json={"enabled": False, "interval_minutes": 30})
        assert response.status_code == 200
        time.sleep(0.1)
        status = client.get("/integrations/large-context-sync/status").json()
        assert status["config"]["enabled"] is False
        assert status["scheduler"]["next_run_at"] is None


def test_manual_run_creates_history_and_updates_provider_state(tmp_path, monkeypatch):
    provider = FakeLiveProvider()
    app, db_path, _ = _make_app(tmp_path, monkeypatch, [provider])

    with TestClient(app) as client:
        response = client.post("/integrations/large-context-sync/run", json={"providers": ["fake_live"]})
        assert response.status_code == 200
        payload = response.json()["run"]
        assert payload["status"] == "completed"
        assert payload["providers_succeeded"] == ["fake_live"]

    state = _fetch_one(db_path, "SELECT status, cursor_json FROM large_context_provider_state WHERE provider = ?", ("fake_live",))
    assert state[0] == "synced"
    assert json.loads(state[1]) == {"since": "cursor-1"}
    run_row = _fetch_one(db_path, "SELECT status FROM large_context_sync_runs ORDER BY started_at DESC LIMIT 1")
    assert run_row[0] == "completed"


def test_disconnected_provider_is_skipped_without_failure(tmp_path, monkeypatch):
    provider = FakeLiveProvider(connected=False)
    app, db_path, _ = _make_app(tmp_path, monkeypatch, [provider])

    with TestClient(app) as client:
        response = client.post("/integrations/large-context-sync/run", json={"providers": ["fake_live"]})
        assert response.status_code == 200
        payload = response.json()["run"]
        assert payload["providers_succeeded"] == []
        assert payload["providers_failed"] == []

    state = _fetch_one(db_path, "SELECT status FROM large_context_provider_state WHERE provider = ?", ("fake_live",))
    assert state[0] == "disconnected"


def test_placeholder_provider_reports_not_supported_and_does_not_write_graph(tmp_path, monkeypatch):
    placeholder = FakePlaceholderProvider()
    app, db_path, _ = _make_app(tmp_path, monkeypatch, [placeholder])

    with TestClient(app) as client:
        response = client.post("/integrations/large-context-sync/run", json={"providers": ["slack"]})
        assert response.status_code == 200
        providers = client.get("/integrations/large-context-sync/providers").json()["providers"]
        assert providers[0]["mode"] == "placeholder"

    state = _fetch_one(db_path, "SELECT status FROM large_context_provider_state WHERE provider = ?", ("slack",))
    assert state[0] == "not_supported_yet"
    graph_rows = _fetch_all(db_path, "SELECT * FROM data_table WHERE category LIKE 'large_context_%'")
    assert graph_rows == []


def test_markdown_and_graph_projection_are_idempotent(tmp_path, monkeypatch):
    provider = FakeLiveProvider()
    app, db_path, data_dir = _make_app(tmp_path, monkeypatch, [provider])

    with TestClient(app) as client:
        assert client.post("/integrations/large-context-sync/run", json={"providers": ["fake_live"]}).status_code == 200
        assert client.post("/integrations/large-context-sync/run", json={"providers": ["fake_live"]}).status_code == 200

    markdown_path = data_dir / "long_term_context" / "fake_live.md"
    content = markdown_path.read_text(encoding="utf-8")
    assert markdown_path.exists()
    assert content.count("### ticket: Fake Ticket") == 1

    entity_rows = _fetch_all(
        db_path,
        """
        SELECT Node_UUID
        FROM data_table
        WHERE category = 'large_context_identity'
          AND key = 'external_id'
          AND info = ?
        """,
        ("fake_live:1",),
    )
    assert len(entity_rows) == 1


def test_failed_provider_does_not_block_later_provider(tmp_path, monkeypatch):
    failing = FakeLiveProvider(provider_id="failing_live", fail=True)
    healthy = FakeLiveProvider(provider_id="healthy_live")
    app, db_path, _ = _make_app(tmp_path, monkeypatch, [failing, healthy])

    with TestClient(app) as client:
        response = client.post(
            "/integrations/large-context-sync/run",
            json={"providers": ["failing_live", "healthy_live"]},
        )
        assert response.status_code == 200
        payload = response.json()["run"]
        assert payload["status"] == "partial_success"
        assert payload["providers_failed"] == ["failing_live"]
        assert payload["providers_succeeded"] == ["healthy_live"]

    failing_state = _fetch_one(db_path, "SELECT status, last_error FROM large_context_provider_state WHERE provider = ?", ("failing_live",))
    healthy_state = _fetch_one(db_path, "SELECT status FROM large_context_provider_state WHERE provider = ?", ("healthy_live",))
    assert failing_state[0] == "error"
    assert "exploded" in failing_state[1]
    assert healthy_state[0] == "synced"


def test_incremental_cursor_and_status_endpoint(tmp_path, monkeypatch):
    provider = FakeLiveProvider()
    app, db_path, _ = _make_app(tmp_path, monkeypatch, [provider])

    with TestClient(app) as client:
        assert client.post("/integrations/large-context-sync/run", json={"providers": ["fake_live"]}).status_code == 200
        assert client.post("/integrations/large-context-sync/run", json={"providers": ["fake_live"]}).status_code == 200
        status = client.get("/integrations/large-context-sync/status")
        assert status.status_code == 200
        payload = status.json()
        assert payload["last_run"]["providers_succeeded"] == ["fake_live"]
        assert any(state["provider"] == "fake_live" for state in payload["providers"])
        assert payload["scheduler"]["running"] is True

    assert provider.received_cursors[0] is None
    assert provider.received_cursors[1] == {"since": "cursor-1"}
    stored_cursor = _fetch_one(db_path, "SELECT cursor_json FROM large_context_provider_state WHERE provider = ?", ("fake_live",))
    assert json.loads(stored_cursor[0]) == {"since": "cursor-2"}


def test_manual_run_accepts_integration_key_alias_for_provider(tmp_path, monkeypatch):
    google_provider = FakeLiveProvider(
        provider_id="google_workspace",
        integration_provider_key="google",
    )
    app, _, _ = _make_app(tmp_path, monkeypatch, [google_provider])

    with TestClient(app) as client:
        response = client.post(
            "/integrations/large-context-sync/run",
            json={"mode": "integrations", "integration_ids": ["google"]},
        )
        assert response.status_code == 200
        payload = response.json()["run"]
        assert payload["providers_succeeded"] == ["google_workspace"]


def test_all_connected_live_mode_runs_connected_live_providers_only(tmp_path, monkeypatch):
    github_provider = FakeLiveProvider(provider_id="github", integration_provider_key="github")
    google_provider = FakeLiveProvider(
        provider_id="google_workspace",
        integration_provider_key="google",
    )
    disconnected_provider = FakeLiveProvider(
        provider_id="notion",
        integration_provider_key="notion",
        connected=False,
    )
    app, _, _ = _make_app(tmp_path, monkeypatch, [github_provider, google_provider, disconnected_provider])

    with TestClient(app) as client:
        response = client.post(
            "/integrations/large-context-sync/run",
            json={"mode": "all_connected_live"},
        )
        assert response.status_code == 200
        payload = response.json()["run"]
        assert payload["providers_attempted"] == ["github", "google_workspace"]
        assert payload["providers_succeeded"] == ["github", "google_workspace"]


def test_legacy_github_only_request_remains_backward_compatible(tmp_path, monkeypatch):
    github_provider = FakeLiveProvider(provider_id="github", integration_provider_key="github")
    google_provider = FakeLiveProvider(
        provider_id="google_workspace",
        integration_provider_key="google",
    )
    app, _, _ = _make_app(tmp_path, monkeypatch, [github_provider, google_provider])

    with TestClient(app) as client:
        response = client.post("/integrations/large-context-sync/run", json={"providers": ["github"]})
        assert response.status_code == 200
        payload = response.json()["run"]
        assert payload["providers_attempted"] == ["github", "google_workspace"]
        assert payload["providers_succeeded"] == ["github", "google_workspace"]


def test_provider_mode_requires_provider_ids_and_rejects_mixed_selectors(tmp_path, monkeypatch):
    provider = FakeLiveProvider()
    app, _, _ = _make_app(tmp_path, monkeypatch, [provider])

    with TestClient(app) as client:
        response = client.post(
            "/integrations/large-context-sync/run",
            json={"mode": "providers", "integration_ids": ["fake_live"]},
        )
        assert response.status_code == 400
        assert "mode='providers'" in response.json()["detail"]

        response = client.post(
            "/integrations/large-context-sync/run",
            json={"providers": ["fake_live"], "provider_ids": ["fake_live"]},
        )
        assert response.status_code == 400
        assert "legacy providers or provider_ids/integration_ids" in response.json()["detail"]


def test_status_exposes_integration_controls_seeded_from_provider_registry(tmp_path, monkeypatch):
    github_provider = FakeLiveProvider(provider_id="github", integration_provider_key="github")
    google_provider = FakeLiveProvider(
        provider_id="google_workspace",
        integration_provider_key="google",
    )
    placeholder = FakePlaceholderProvider()
    app, db_path, _ = _make_app(tmp_path, monkeypatch, [github_provider, google_provider, placeholder])

    with TestClient(app) as client:
        response = client.get("/integrations/large-context-sync/status")
        assert response.status_code == 200
        payload = response.json()
        integrations = {item["integration_id"]: item for item in payload["integrations"]}
        assert sorted(integrations) == ["github", "google"]
        assert integrations["github"]["provider_ids"] == ["github"]
        assert integrations["google"]["provider_ids"] == ["google_workspace"]
        assert integrations["github"]["enabled"] is True
        assert integrations["github"]["interval_minutes"] == 60
        assert integrations["github"]["next_run_at"] is not None

    rows = _fetch_all(
        db_path,
        "SELECT integration_id, enabled, interval_minutes FROM large_context_integration_controls ORDER BY integration_id",
    )
    assert rows == [("github", 1, 60), ("google", 1, 60)]


def test_put_integration_config_updates_only_target_integration(tmp_path, monkeypatch):
    github_provider = FakeLiveProvider(provider_id="github", integration_provider_key="github")
    google_provider = FakeLiveProvider(
        provider_id="google_workspace",
        integration_provider_key="google",
    )
    app, db_path, _ = _make_app(tmp_path, monkeypatch, [github_provider, google_provider])

    with TestClient(app) as client:
        response = client.put(
            "/integrations/large-context-sync/integrations/google",
            json={"enabled": False, "interval_minutes": 120},
        )
        assert response.status_code == 200
        status = client.get("/integrations/large-context-sync/status").json()
        integrations = {item["integration_id"]: item for item in status["integrations"]}
        assert integrations["google"]["enabled"] is False
        assert integrations["google"]["interval_minutes"] == 120
        assert integrations["google"]["next_run_at"] is None
        assert integrations["github"]["enabled"] is True
        assert integrations["github"]["interval_minutes"] == 60

    rows = _fetch_all(
        db_path,
        "SELECT integration_id, enabled, interval_minutes FROM large_context_integration_controls ORDER BY integration_id",
    )
    assert rows == [("github", 1, 60), ("google", 0, 120)]


def test_scheduler_resolves_due_enabled_connected_integrations(tmp_path, monkeypatch):
    github_provider = FakeLiveProvider(provider_id="github", integration_provider_key="github")
    google_provider = FakeLiveProvider(
        provider_id="google_workspace",
        integration_provider_key="google",
    )
    app, db_path, _ = _make_app(tmp_path, monkeypatch, [github_provider, google_provider])

    future_completed_at = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
    past_completed_at = (datetime.now(timezone.utc) - timedelta(minutes=90)).isoformat()
    from server.fastapi_app.dependencies import get_encrypted_conn

    with get_encrypted_conn(str(db_path)) as conn:
        conn.execute(
            """
            UPDATE large_context_integration_controls
            SET interval_minutes = CASE integration_id
                WHEN 'github' THEN 30
                WHEN 'google' THEN 120
                ELSE interval_minutes
            END,
                last_completed_at = CASE integration_id
                WHEN 'github' THEN ?
                WHEN 'google' THEN ?
                ELSE last_completed_at
            END
            """,
            (past_completed_at, future_completed_at),
        )
        conn.commit()

    with TestClient(app) as client:
        scheduler = client.app.state.large_context_sync_service.scheduler
        due, next_run_at = scheduler._resolve_due_integrations(datetime.now(timezone.utc))
        assert due == ["github"]
        assert next_run_at is not None


def test_integration_status_aggregates_multiple_provider_results(tmp_path, monkeypatch):
    gmail_provider = FakeLiveProvider(
        provider_id="gmail",
        integration_provider_key="google",
    )
    drive_provider = FakeLiveProvider(
        provider_id="gdrive",
        integration_provider_key="google",
        fail=True,
    )
    app, _, _ = _make_app(tmp_path, monkeypatch, [gmail_provider, drive_provider])

    with TestClient(app) as client:
        response = client.post(
            "/integrations/large-context-sync/run",
            json={"mode": "integrations", "integration_ids": ["google"]},
        )
        assert response.status_code == 200
        payload = client.get("/integrations/large-context-sync/status").json()
        integrations = {item["integration_id"]: item for item in payload["integrations"]}
        google = integrations["google"]
        assert google["provider_ids"] == ["gmail", "gdrive"]
        assert google["status"] == "partial_success"
        assert google["last_success_at"] is not None
        assert "gdrive" in (google["last_error"] or "")


def test_manual_run_returns_409_when_another_run_is_active(tmp_path, monkeypatch):
    provider = FakeLiveProvider(sleep_seconds=0.4)
    app, _, _ = _make_app(tmp_path, monkeypatch, [provider])

    with TestClient(app) as client:
        first_response: list[int] = []

        def run_sync():
            response = client.post("/integrations/large-context-sync/run", json={"providers": ["fake_live"]})
            first_response.append(response.status_code)

        worker = threading.Thread(target=run_sync)
        worker.start()
        time.sleep(0.1)

        second = client.post("/integrations/large-context-sync/run", json={"providers": ["fake_live"]})
        worker.join()

        assert second.status_code == 409
        assert first_response == [200]
