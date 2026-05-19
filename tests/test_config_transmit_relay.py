"""Tests for transmit + relay settings on /api/config."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.routes import config_routes as config_module


def _build_app() -> FastAPI:
    app = FastAPI()
    app.include_router(config_module.router)
    return app


def _reset_config_state() -> None:
    config_module._config = None
    config_module._crypto = None
    config_module._tx_service = None


def _fake_config(*, relay_enabled=False, max_relay_per_minute=20):
    cfg = MagicMock()
    cfg.radio.region = "US"
    cfg.radio.frequency_mhz = 906.875
    cfg.radio.spreading_factor = 11
    cfg.radio.bandwidth_khz = 250.0
    cfg.radio.coding_rate = "4/5"
    cfg.radio.sync_word = 0x2B
    cfg.radio.preamble_length = 16
    cfg.transmit.enabled = True
    cfg.transmit.node_id = 0xDEADBEEF
    cfg.transmit.tx_power_dbm = 27
    cfg.transmit.max_duty_cycle_percent = None
    cfg.transmit.long_name = "Meshpoint"
    cfg.transmit.short_name = "MP"
    cfg.transmit.hop_limit = 3
    cfg.transmit.nodeinfo = MagicMock()
    cfg.relay.enabled = relay_enabled
    cfg.relay.max_relay_per_minute = max_relay_per_minute
    cfg.meshtastic.primary_channel_name = "LongFast"
    cfg.meshtastic.default_key_b64 = "AQ=="
    cfg.meshtastic.channel_keys = {}
    cfg.meshcore.channel_keys = {}
    return cfg


class TestGetConfigRelay(unittest.TestCase):
    def setUp(self):
        _reset_config_state()
        config_module._config = _fake_config(relay_enabled=True, max_relay_per_minute=42)
        self.client = TestClient(_build_app())

    def tearDown(self):
        _reset_config_state()

    def test_transmit_block_includes_relay(self):
        resp = self.client.get("/api/config")
        self.assertEqual(resp.status_code, 200)
        relay = resp.json()["transmit"]["relay"]
        self.assertTrue(relay["enabled"])
        self.assertEqual(relay["max_relay_per_minute"], 42)

    def test_top_level_relay_block(self):
        resp = self.client.get("/api/config")
        relay = resp.json()["relay"]
        self.assertTrue(relay["enabled"])
        self.assertEqual(relay["max_relay_per_minute"], 42)


class TestUpdateTransmitRelay(unittest.TestCase):
    def setUp(self):
        _reset_config_state()
        self.cfg = _fake_config()
        config_module._config = self.cfg
        self.client = TestClient(_build_app())

    def tearDown(self):
        _reset_config_state()

    def test_relay_settings_persist_to_yaml(self):
        with patch("src.api.routes.config_routes.save_section_to_yaml") as mock_save:
            resp = self.client.put(
                "/api/config/transmit",
                json={
                    "relay": {"enabled": True, "max_relay_per_minute": 15},
                },
            )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue(body["saved"])
        self.assertTrue(body["restart_required"])
        self.assertEqual(body["updates"]["relay"]["max_relay_per_minute"], 15)
        self.assertTrue(self.cfg.relay.enabled)
        self.assertEqual(self.cfg.relay.max_relay_per_minute, 15)
        mock_save.assert_called_once_with(
            "relay",
            {"enabled": True, "max_relay_per_minute": 15},
        )

    def test_relay_rate_out_of_range_rejected(self):
        resp = self.client.put(
            "/api/config/transmit",
            json={"relay": {"max_relay_per_minute": 999}},
        )
        self.assertEqual(resp.status_code, 400)


if __name__ == "__main__":
    unittest.main()
