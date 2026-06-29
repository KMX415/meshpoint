"""Quick Deploy public channel export."""

from __future__ import annotations

import base64
import unittest

from meshtastic.protobuf import apponly_pb2

from src.config import AppConfig, MeshtasticConfig, RadioConfig, TransmitConfig
from src.config_export import build_quick_deploy_export


class TestConfigExport(unittest.TestCase):
    def test_export_uses_public_default_psk_only(self) -> None:
        cfg = AppConfig()
        cfg.radio = RadioConfig(
            region="US",
            frequency_mhz=906.875,
            spreading_factor=11,
            bandwidth_khz=250.0,
            coding_rate="4/5",
        )
        cfg.meshtastic = MeshtasticConfig(
            primary_channel_name="LongFast",
            default_key_b64="wLvS00jm+SlCkdkZ6DRZXvLoqoSgPT+3vh8zX+MJoyQ=",
            channel_keys={"SecretChat": "anotherBase64PSK=="},
        )
        cfg.transmit = TransmitConfig(hop_limit=3)

        payload = build_quick_deploy_export(cfg)

        self.assertFalse(payload["psk_included"])
        self.assertNotIn("channel_keys", payload)
        self.assertNotIn("psk_b64", payload)
        self.assertEqual(payload["channel_name"], "LongFast")
        self.assertEqual(payload["modem_preset"], "LONG_FAST")
        self.assertTrue(payload["meshtastic_url"].startswith("https://meshtastic.org/e/#"))

        fragment = payload["meshtastic_url"].split("/#", 1)[1]
        padding = "=" * ((4 - len(fragment) % 4) % 4)
        raw = base64.urlsafe_b64decode(fragment + padding)
        channel_set = apponly_pb2.ChannelSet()
        channel_set.ParseFromString(raw)
        self.assertEqual(len(channel_set.settings), 1)
        self.assertEqual(channel_set.settings[0].name, "LongFast")
        self.assertEqual(bytes(channel_set.settings[0].psk), b"\x01")

    def test_eu_region_maps_in_url(self) -> None:
        cfg = AppConfig()
        cfg.radio = RadioConfig(
            region="EU_868",
            frequency_mhz=869.525,
            spreading_factor=11,
            bandwidth_khz=250.0,
            coding_rate="4/5",
        )
        payload = build_quick_deploy_export(cfg)
        self.assertEqual(payload["region"], "EU_868")
        self.assertIn("meshtastic.org/e/#", payload["meshtastic_url"])


if __name__ == "__main__":
    unittest.main()
