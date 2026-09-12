"""Public summaries remain opt-in, page-scoped and separate from authenticated APIs."""

from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from src.api.audit import AuditLogWriter
from src.api.auth import auth_bootstrap, dependencies
from src.api.auth.jwt_session import JwtSessionService
from src.api.routes import stats_routes
from src.api import server
from src.config import AppConfig


@pytest.fixture
def public_app(tmp_path, monkeypatch):
    config = AppConfig()
    config.storage.database_path = str(tmp_path / "test.db")
    config.dashboard.static_dir = str(Path(__file__).resolve().parents[1] / "frontend")
    config.web_auth.jwt_secret = "public-view-test-" + "x" * 32
    config.web_auth.admin_password_hash = "test-setup-complete"
    persisted = []
    monkeypatch.setattr(auth_bootstrap, "_make_persister", lambda: persisted.append)
    writer = AuditLogWriter(log_path=tmp_path / "audit.jsonl")
    monkeypatch.setattr(server, "AuditLogWriter", lambda: writer)
    nodes = AsyncMock()
    nodes.get_count.return_value = 25
    nodes.get_active_count.return_value = 8
    traffic = AsyncMock()
    traffic.get_traffic_summary.return_value = {
        "total_packets": 300, "packets_last_hour": 60, "packets_per_minute": 1,
        "private_field": "MUST-NOT-LEAK",
    }
    signal = AsyncMock()
    signal.get_signal_summary.return_value = {
        "avg_rssi": -90, "avg_snr": 7, "private_field": "MUST-NOT-LEAK",
    }
    monkeypatch.setattr(stats_routes, "_node_repo", nodes)
    monkeypatch.setattr(stats_routes, "_traffic_monitor", traffic)
    monkeypatch.setattr(stats_routes, "_signal_analyzer", signal)
    app = server.create_app(config)
    jwt = JwtSessionService(config.web_auth.jwt_secret, 60, 1)
    anonymous, admin, viewer = (TestClient(app) for _ in range(3))
    admin.headers["Authorization"] = f"Bearer {jwt.issue('admin', 'admin')}"
    admin.cookies.set("meshpoint_session", jwt.issue("admin", "admin"))
    viewer.headers["Authorization"] = f"Bearer {jwt.issue('viewer', 'viewer')}"
    yield config, anonymous, admin, viewer, persisted
    dependencies.reset_auth()


def enable(admin, pages):
    result = admin.put("/api/config/public_view", json={"enabled": True, "pages": pages})
    assert result.status_code == 200
    return result


def test_default_disabled(public_app):
    config, public, _, _, _ = public_app
    assert config.web_auth.public_view_enabled is False
    assert public.get("/", follow_redirects=False).headers["location"] == "/login"
    for path in ("", "/dashboard", "/stats", "/radio"):
        assert public.get("/api/public/view" + path).status_code == 404


def test_setup_required_even_if_enabled(public_app):
    config, public, admin, _, _ = public_app
    enable(admin, ["dashboard"])
    config.web_auth.admin_password_hash = ""
    assert public.get("/api/public/view").status_code == 404
    assert public.get("/", follow_redirects=False).headers["location"] == "/setup"


def test_only_admin_can_configure_and_values_persist(public_app):
    config, public, admin, viewer, persisted = public_app
    payload = {"enabled": True, "pages": ["dashboard", "radio"]}
    assert public.put("/api/config/public_view", json=payload).status_code == 401
    assert viewer.put("/api/config/public_view", json=payload).status_code == 403
    assert persisted == []
    enable(admin, payload["pages"])
    assert persisted == [{"public_view_enabled": True, "public_view_pages": payload["pages"]}]
    assert config.web_auth.public_view_enabled
    settings = admin.get("/api/config/auth_settings").json()
    assert settings["public_view_pages"] == payload["pages"]


@pytest.mark.parametrize("pages", [[], ["messages"], ["configuration"], ["../config"]])
def test_invalid_selection_rejected(public_app, pages):
    config, _, admin, _, persisted = public_app
    assert admin.put("/api/config/public_view", json={"enabled": True, "pages": pages}).status_code == 422
    assert not config.web_auth.public_view_enabled
    assert persisted == []


def test_selected_pages_and_explicit_fields_only(public_app):
    config, public, admin, _, _ = public_app
    enable(admin, ["dashboard", "stats", "radio"])
    assert public.get("/api/public/view").json() == {"pages": ["dashboard", "stats", "radio"]}
    dashboard = public.get("/api/public/view/dashboard")
    assert dashboard.json() == {"total_nodes": 25, "active_24h": 8}
    assert dashboard.headers["cache-control"] == "no-store"
    assert "set-cookie" not in dashboard.headers
    assert public.get("/api/public/view/stats").json() == {
        "total_packets": 300, "packets_last_hour": 60,
        "packets_per_minute": 1, "avg_rssi": -90, "avg_snr": 7,
    }
    assert public.get("/api/public/view/radio").json() == {
        "region": config.radio.region, "frequency_mhz": config.radio.frequency_mhz,
        "bandwidth_khz": config.radio.bandwidth_khz, "spreading_factor": config.radio.spreading_factor,
    }
    assert public.get("/api/public/view/messages").status_code == 404


def test_revocation_blocks_cached_page_immediately(public_app):
    _, public, admin, _, _ = public_app
    enable(admin, ["dashboard", "radio"])
    assert public.get("/api/public/view/radio").status_code == 200
    enable(admin, ["dashboard"])
    assert public.get("/api/public/view/radio").status_code == 404
    assert public.get("/api/public/view/dashboard").status_code == 200
    assert admin.put("/api/config/public_view", json={"enabled": False, "pages": []}).status_code == 200
    assert public.get("/api/public/view/dashboard").status_code == 404
    assert public.get("/", follow_redirects=False).status_code == 302


def test_public_landing_does_not_unlock_private_routes_or_socket(public_app):
    _, public, admin, _, _ = public_app
    enable(admin, ["dashboard"])
    html = public.get("/")
    assert html.status_code == 200
    assert "Admin sign in" in html.text
    assert "js/app.js" not in html.text
    assert "js/app.js" in admin.get("/").text
    assert public.get("/login").status_code == 200
    for path in ("/api/config", "/api/messages/conversations", "/api/nodes", "/api/stats/summary"):
        assert public.get(path).status_code == 401
    with public.websocket_connect("/ws") as ws:
        with pytest.raises(WebSocketDisconnect) as exc:
            ws.receive_json()
        assert exc.value.code == 4401


def test_failed_persistence_keeps_public_disabled(public_app, monkeypatch):
    from src.api.routes import auth_config_routes
    config, _, _, _, _ = public_app

    def fail(_values):
        raise OSError("test failure")

    service = auth_config_routes._service()
    monkeypatch.setattr(service, "_persist", fail)
    with pytest.raises(OSError):
        service.update_public_view(True, ["radio"])
    assert not config.web_auth.public_view_enabled


def test_revocation_during_query(public_app, monkeypatch):
    config, public, admin, _, _ = public_app
    enable(admin, ["dashboard"])

    async def revoke(_page):
        config.web_auth.public_view_enabled = False
        return {"total_nodes": 25}

    monkeypatch.setattr(stats_routes, "public_snapshot", revoke)
    assert public.get("/api/public/view/dashboard").status_code == 404


def test_startup_has_no_fabricated_counts(public_app, monkeypatch):
    _, public, admin, _, _ = public_app
    enable(admin, ["dashboard"])
    monkeypatch.setattr(stats_routes, "_node_repo", None)
    assert public.get("/api/public/view/dashboard").status_code == 503


def test_repeated_requests_share_aggregate_cache(public_app):
    _, public, admin, _, _ = public_app
    enable(admin, ["dashboard"])
    assert public.get("/api/public/view/dashboard").status_code == 200
    assert public.get("/api/public/view/dashboard").status_code == 200
    stats_routes._node_repo.get_count.assert_awaited_once()
