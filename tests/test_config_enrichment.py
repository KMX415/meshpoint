"""Tests for GET /api/config enrichment (platform + meshtasticd)."""

import unittest
from unittest.mock import MagicMock

from src.api.routes.config_enrichment import enrich_config_payload
from src.config import AppConfig, DeviceConfig, CaptureConfig, MeshtasticdConfig


class TestConfigEnrichment(unittest.TestCase):
    def _node_config(self) -> AppConfig:
        cfg = AppConfig()
        cfg.device = DeviceConfig(platform="node")
        cfg.capture = CaptureConfig(
            sources=["meshtasticd"],
            meshtasticd=MeshtasticdConfig(
                host="127.0.0.1",
                port=4403,
                preset="rak13302-1w.yaml",
            ),
        )
        return cfg

    def test_gateway_has_platform_gateway(self):
        cfg = AppConfig()
        cfg.device.platform = "gateway"
        out = enrich_config_payload(cfg, {})
        self.assertEqual(out["device"]["platform"], "gateway")
        self.assertNotIn("platform_ui", out)

    def test_node_exposes_meshtasticd_and_variant(self):
        cfg = self._node_config()
        out = enrich_config_payload(cfg, {})
        self.assertEqual(out["device"]["platform"], "node")
        self.assertEqual(out["platform_ui"]["variant"], "wismesh_node")
        self.assertEqual(out["capture"]["meshtasticd"]["port"], 4403)
        self.assertEqual(out["capture"]["meshtasticd"]["module_badge"], "RAK13302")
        self.assertTrue(out["capture"]["meshcore_usb_auto_detect_suppressed"])

    def test_node_runtime_from_bridge_provider(self):
        cfg = self._node_config()
        source = MagicMock()
        source.is_running = True
        source.request_read_radio_state.return_value = (
            True,
            {"long_name": "Pi Node", "short_name": "PN", "bridge_connected": True},
        )
        out = enrich_config_payload(
            cfg,
            {},
            bridge_status_provider=lambda: source,
        )
        self.assertTrue(out["meshtasticd_runtime"]["bridge_connected"])
        self.assertEqual(out["meshtasticd_runtime"]["long_name"], "Pi Node")


if __name__ == "__main__":
    unittest.main()
