"""Tests for Configuration → MQTT API routes."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.auth.dependencies import require_admin
from src.api.auth.jwt_session import ROLE_ADMIN, SessionClaims
from src.api.routes import mqtt_config_routes as mqtt_module
from src.config import MqttConfig
from src.relay.mqtt_publisher import _resolve_gateway_id


def _admin_claims() -> SessionClaims:
    return SessionClaims(subject="admin", role=ROLE_ADMIN, session_version=1)


def _build_app() -> FastAPI:
    app = FastAPI()
    app.dependency_overrides[require_admin] = _admin_claims
    app.include_router(mqtt_module.router)
    return app


def _fake_app_config(*, device_name: str = "meshpoint-test"):
    cfg = MagicMock()
    cfg.mqtt = MqttConfig(
        enabled=False,
        broker="mqtt.meshtastic.org",
        port=1883,
        topic_root="msh",
        region="US",
    )
    cfg.device.device_name = device_name
    return cfg


class TestBuildMqttStatus(unittest.TestCase):
    def test_maps_yaml_fields_to_dashboard_shape(self) -> None:
        mqtt = MqttConfig(
            enabled=True,
            broker="broker.example.com",
            port=8883,
            topic_root="msh",
            region="EU_868",
            publish_json=True,
            publish_channels=["LongFast", "MyPrivate"],
            location_precision="approximate",
            homeassistant_discovery=True,
        )
        status = mqtt_module.build_mqtt_status(mqtt, "My Meshpoint")
        self.assertTrue(status["enabled"])
        self.assertEqual(status["broker_host"], "broker.example.com")
        self.assertEqual(status["broker_port"], 8883)
        self.assertEqual(status["region_segment"], "EU_868")
        self.assertTrue(status["publish_json"])
        self.assertEqual(status["publish_channels"], ["LongFast", "MyPrivate"])
        self.assertEqual(status["location_precision"], "approximate")
        self.assertTrue(status["homeassistant_discovery"])
        self.assertTrue(status["gateway_id"].startswith("!"))
        self.assertIn("/2/e/", status["topic_preview_meshtastic"])


class TestUpdateMqttRoute(unittest.TestCase):
    def setUp(self) -> None:
        mqtt_module._config = _fake_app_config()
        self.client = TestClient(_build_app())

    def tearDown(self) -> None:
        mqtt_module.reset_routes()

    def test_round_trip_persists_yaml(self) -> None:
        with patch("src.api.routes.mqtt_config_routes.save_section_to_yaml") as mock_save:
            resp = self.client.put(
                "/api/config/mqtt",
                json={
                    "enabled": True,
                    "broker_host": "mqtt.example.com",
                    "broker_port": 1883,
                    "username": "user1",
                    "password": "secret",
                    "password_unchanged": False,
                    "topic_root": "msh",
                    "region_segment": "ANZ",
                    "gateway_id": "",
                    "publish_channels": ["LongFast", "MeshCore"],
                    "publish_json": False,
                    "location_precision": "none",
                    "homeassistant_discovery": False,
                },
            )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue(body["saved"])
        self.assertTrue(body["restart_required"])
        self.assertEqual(body["mqtt"]["broker_host"], "mqtt.example.com")
        self.assertEqual(body["mqtt"]["region_segment"], "ANZ")
        mock_save.assert_called_once()
        saved = mock_save.call_args[0][1]
        self.assertEqual(saved["broker"], "mqtt.example.com")
        self.assertEqual(saved["region"], "ANZ")
        self.assertFalse(saved["publish_json"])
        self.assertEqual(saved["password"], "secret")

    def test_invalid_gateway_id_returns_400(self) -> None:
        resp = self.client.put(
            "/api/config/mqtt",
            json={
                "enabled": False,
                "broker_host": "mqtt.example.com",
                "broker_port": 1883,
                "topic_root": "msh",
                "region_segment": "US",
                "publish_channels": ["LongFast"],
                "gateway_id": "not-valid",
            },
        )
        self.assertEqual(resp.status_code, 400)

    def test_empty_publish_channels_returns_422(self) -> None:
        resp = self.client.put(
            "/api/config/mqtt",
            json={
                "enabled": True,
                "broker_host": "mqtt.example.com",
                "broker_port": 1883,
                "topic_root": "msh",
                "region_segment": "US",
                "publish_channels": ["", "  "],
            },
        )
        self.assertEqual(resp.status_code, 422)


class TestMqttRuntimeRoute(unittest.TestCase):
    def tearDown(self) -> None:
        mqtt_module.reset_routes()

    def test_runtime_disabled_when_mqtt_off(self) -> None:
        mqtt_module.init_routes(_fake_app_config())
        client = TestClient(_build_app())
        resp = client.get("/api/config/mqtt/runtime")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertFalse(body["config_enabled"])
        self.assertFalse(body["publisher_active"])
        self.assertFalse(body["connected"])

    def test_runtime_reflects_live_publisher(self) -> None:
        publisher = MagicMock()
        publisher.get_runtime_status.return_value = {
            "connected": True,
            "publish_count": 42,
            "disconnect_count": 1,
            "last_connect_rc": 0,
            "last_disconnect_rc": None,
            "last_publish_at": "2026-06-11T12:00:00+00:00",
            "connected_since": "2026-06-11T11:00:00+00:00",
            "topic_prefix": "msh/US",
            "gateway_id": "!aabbccdd",
            "broker_host": "broker.example.com",
            "broker_port": 1883,
        }
        cfg = _fake_app_config()
        cfg.mqtt.enabled = True
        mqtt_module.init_routes(cfg, mqtt_publisher=publisher)
        client = TestClient(_build_app())
        resp = client.get("/api/config/mqtt/runtime")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue(body["config_enabled"])
        self.assertTrue(body["publisher_active"])
        self.assertTrue(body["connected"])
        self.assertEqual(body["publish_count"], 42)
        self.assertEqual(body["topic_prefix"], "msh/US")


class TestResolveGatewayId(unittest.TestCase):
    def test_override_wins_over_device_name(self) -> None:
        self.assertEqual(
            _resolve_gateway_id("aabbccdd", "anything"),
            "!aabbccdd",
        )

    def test_auto_derived_when_override_blank(self) -> None:
        gid = _resolve_gateway_id(None, "meshpoint-alpha")
        self.assertTrue(gid.startswith("!"))
        self.assertEqual(len(gid), 9)
