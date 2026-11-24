"""The topbar can report USB capture independently from native transmit."""

import asyncio
from types import SimpleNamespace

from src.api.auth.jwt_session import ROLE_ADMIN, SessionClaims
from src.api.routes import config_routes
from src.config import AppConfig


def test_config_reports_live_meshcore_capture_when_transmit_is_disabled(monkeypatch):
    config = AppConfig()
    config.capture.sources = ["meshcore_usb"]
    config.transmit.enabled = False
    source = SimpleNamespace(connected=True)
    monkeypatch.setattr(config_routes, "_config", config)
    monkeypatch.setattr(config_routes, "_tx_service", None)
    monkeypatch.setattr(config_routes, "_meshcore_sources", [source])
    claims = SessionClaims(subject="test", role=ROLE_ADMIN, session_version=1)

    connected = asyncio.run(config_routes.get_config(claims))["meshcore"]
    assert connected["capture_connected"] is True
    assert connected["connected"] is False
    assert connected["status_note"] == "transmit_disabled"

    source.connected = False
    disconnected = asyncio.run(config_routes.get_config(claims))["meshcore"]
    assert disconnected["capture_connected"] is False
