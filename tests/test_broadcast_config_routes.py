"""Tests for position and telemetry broadcast config routes."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.routes import position_broadcast_routes as pos_module
from src.api.routes import telemetry_broadcast_routes as telem_module
from src.config import AppConfig, load_config


def _fake_config() -> AppConfig:
    return load_config()


def _build_app() -> FastAPI:
    app = FastAPI()
    app.include_router(pos_module.router)
    app.include_router(telem_module.router)
    from tests.auth_test_helpers import override_as_admin
    override_as_admin(app)
    return app


def _reset():
    pos_module._config = None
    pos_module._position_broadcaster = None
    telem_module._config = None
    telem_module._telemetry_broadcaster = None


class TestPositionBroadcastRoutes(unittest.TestCase):
    def setUp(self):
        _reset()
        self.client = TestClient(_build_app())
        pos_module.init_routes(_fake_config())

    def tearDown(self):
        _reset()

    def test_503_when_config_missing(self):
        pos_module._config = None
        res = self.client.put(
            "/api/config/position",
            json={"interval_minutes": 30},
        )
        self.assertEqual(res.status_code, 503)

    def test_400_on_invalid_interval(self):
        res = self.client.put(
            "/api/config/position",
            json={"interval_minutes": 4},
        )
        self.assertEqual(res.status_code, 400)

    def test_zero_interval_saved(self):
        with patch.object(pos_module, "save_section_to_yaml") as mock_save:
            res = self.client.put(
                "/api/config/position",
                json={"interval_minutes": 0},
            )
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertTrue(body["saved"])
        self.assertEqual(body["updates"]["interval_minutes"], 0)
        mock_save.assert_called_once()

    def test_hot_reload_when_broadcaster_running(self):
        broadcaster = MagicMock()
        broadcaster.is_running = True
        broadcaster.set_interval.return_value = 60
        pos_module.init_routes(_fake_config(), broadcaster)
        with patch.object(pos_module, "save_section_to_yaml"):
            res = self.client.put(
                "/api/config/position",
                json={"interval_minutes": 60},
            )
        body = res.json()
        self.assertTrue(body["interval_hot_reloaded"])
        self.assertFalse(body["restart_required"])
        broadcaster.set_interval.assert_called_once_with(60)


class TestTelemetryBroadcastRoutes(unittest.TestCase):
    def setUp(self):
        _reset()
        self.client = TestClient(_build_app())
        telem_module.init_routes(_fake_config())

    def tearDown(self):
        _reset()

    def test_400_on_interval_above_max(self):
        res = self.client.put(
            "/api/config/telemetry",
            json={"interval_minutes": 2000},
        )
        self.assertEqual(res.status_code, 400)

    def test_valid_interval_saved(self):
        with patch.object(telem_module, "save_section_to_yaml") as mock_save:
            res = self.client.put(
                "/api/config/telemetry",
                json={"interval_minutes": 30},
            )
        self.assertEqual(res.status_code, 200)
        mock_save.assert_called_once()
        saved = mock_save.call_args.args[1]["telemetry"]
        self.assertEqual(saved["interval_minutes"], 30)

    def test_restart_required_when_broadcaster_not_running(self):
        with patch.object(telem_module, "save_section_to_yaml"):
            res = self.client.put(
                "/api/config/telemetry",
                json={"interval_minutes": 15},
            )
        body = res.json()
        self.assertTrue(body["restart_required"])
        self.assertFalse(body["interval_hot_reloaded"])
