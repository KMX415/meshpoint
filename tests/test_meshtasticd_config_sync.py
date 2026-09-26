"""Tests for meshtasticd config sync."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from src.capture.meshtasticd_config_sync import (
    MeshtasticdSyncSettings,
    build_sync_settings_from_config,
    sync_meshtasticd_config,
)


class TestMeshtasticdConfigSync(unittest.TestCase):
    def test_build_sync_settings_from_config(self):
        config = MagicMock()
        config.radio.region = "EU_868"
        config.meshtastic.primary_channel_name = "LongFast"

        settings = build_sync_settings_from_config(config)

        self.assertEqual(settings.region, "EU_868")
        self.assertEqual(settings.primary_channel_name, "LongFast")

    @patch("meshtastic.protobuf.config_pb2")
    def test_sync_updates_unset_region(self, mock_config_pb2):
        mock_config_pb2.Config.LoRaConfig.RegionCode.Value.side_effect = lambda n: {
            "US": 1,
        }[n]
        mock_config_pb2.Config.LoRaConfig.RegionCode.Name.return_value = "UNSET"
        mock_config_pb2.Config.LoRaConfig.ModemPreset.Value.return_value = 0

        node = MagicMock()
        node.localConfig.lora.region = 0
        node.localConfig.lora.modem_preset = 0
        node.getChannelByChannelIndex.return_value = MagicMock(
            settings=MagicMock(name="")
        )
        node.channels = [node.getChannelByChannelIndex.return_value]

        iface = MagicMock(localNode=node)
        sync_meshtasticd_config(
            iface,
            MeshtasticdSyncSettings(region="US", primary_channel_name="LongFast"),
        )

        node.writeConfig.assert_called()
        node.writeChannel.assert_called_with(0)
        self.assertEqual(node.localConfig.lora.region, 1)
        self.assertEqual(
            node.getChannelByChannelIndex.return_value.settings.name,
            "LongFast",
        )

    def test_sync_skips_without_local_node(self):
        sync_meshtasticd_config(
            MagicMock(localNode=None),
            MeshtasticdSyncSettings(region="US", primary_channel_name="LongFast"),
        )
