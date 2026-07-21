"""Tests for SerialRadioHandshake connect-time LoRa readout.

Needs the real ``meshtastic`` package (protobuf enums). Same convention
as other serial-adjacent tests.

Credit: javastraat/meshpoint ``77cdaa2`` + ``dc3fc0a``.
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from meshtastic.protobuf import channel_pb2, config_pb2  # noqa: F401

from src.capture.serial_radio_handshake import SerialRadioHandshake
from src.capture.serial_source import SerialCaptureSource
from src.radio.channel_frequency import resolve_frequency_mhz


def _mock_primary_channel(name: str):
    ch = MagicMock()
    ch.role = channel_pb2.Channel.Role.PRIMARY
    ch.settings.name = name
    return ch


class ReadRadioInfoLongFastPresetTest(unittest.TestCase):
    def test_eu433_longfast_preset(self):
        iface = MagicMock()
        iface.localNode.localConfig.lora.channel_num = 0
        iface.localNode.localConfig.lora.region = 2  # EU_433
        iface.localNode.localConfig.lora.use_preset = True
        iface.localNode.localConfig.lora.modem_preset = 0  # LONG_FAST
        iface.localNode.localConfig.lora.frequency_offset = 0.0
        iface.localNode.localConfig.lora.override_frequency = 0.0
        iface.localNode.channels = [_mock_primary_channel("")]
        iface.getShortName.return_value = "EMC3"
        iface.getLongName.return_value = "Meshpoint433"

        info = SerialRadioHandshake.read(iface)

        self.assertEqual(info["region"], "EU_433")
        self.assertEqual(info["channel_num"], 0)
        self.assertEqual(info["modem_preset"], "LONG_FAST")
        self.assertTrue(info["use_preset"])
        self.assertEqual(info["channel_name"], "")
        self.assertEqual(info["spreading_factor"], 11)
        self.assertEqual(info["bandwidth_khz"], 250)
        self.assertEqual(info["coding_rate"], "4/5")
        self.assertEqual(info["short_name"], "EMC3")
        self.assertEqual(info["long_name"], "Meshpoint433")

    def test_reads_primary_channel_name_when_set(self):
        iface = MagicMock()
        iface.localNode.channels = [
            _mock_primary_channel("MyCustomChannel"),
        ]
        name = SerialRadioHandshake.read_primary_channel_name(iface)
        self.assertEqual(name, "MyCustomChannel")

    def test_default_frequency_matches_eu433_preset_default_channel(self):
        freq = resolve_frequency_mhz(
            region="EU_433",
            channel_num=0,
            bandwidth_khz=250,
            channel_name="",
            modem_preset="LONG_FAST",
            use_preset=True,
        )
        self.assertEqual(freq, 433.875)

    def test_default_frequency_matches_eu868_preset_default_channel(self):
        freq = resolve_frequency_mhz(
            region="EU_868",
            channel_num=0,
            bandwidth_khz=250,
            channel_name="AnythingAtAll",
            modem_preset="LONG_FAST",
        )
        self.assertEqual(freq, 869.525)


class ReadRadioInfoCustomConfigTest(unittest.TestCase):
    def test_custom_config_reads_raw_fields(self):
        iface = MagicMock()
        iface.localNode.localConfig.lora.channel_num = 3
        iface.localNode.localConfig.lora.region = 3  # EU_868
        iface.localNode.localConfig.lora.use_preset = False
        iface.localNode.localConfig.lora.spread_factor = 9
        iface.localNode.localConfig.lora.bandwidth = 125
        iface.localNode.localConfig.lora.coding_rate = 6
        iface.localNode.localConfig.lora.frequency_offset = 0.0
        iface.localNode.localConfig.lora.override_frequency = 0.0
        iface.localNode.channels = [_mock_primary_channel("")]
        iface.getShortName.return_value = "CUST"
        iface.getLongName.return_value = "CustomNode"

        info = SerialRadioHandshake.read(iface)

        self.assertEqual(info["modem_preset"], "CUSTOM")
        self.assertFalse(info["use_preset"])
        self.assertEqual(info["spreading_factor"], 9)
        self.assertEqual(info["bandwidth_khz"], 125.0)
        self.assertEqual(info["coding_rate"], "4/6")

    def test_non_default_channel_num_uses_explicit_slot(self):
        freq = resolve_frequency_mhz(
            region="EU_433", channel_num=3, bandwidth_khz=250
        )
        self.assertEqual(freq, 433.625)


class ReadRadioInfoFailureIsolationTest(unittest.TestCase):
    def test_broken_interface_returns_none_filled_dict_not_raise(self):
        iface = MagicMock()
        del iface.localNode
        iface.getShortName.side_effect = Exception("boom")

        info = SerialRadioHandshake.read(iface)

        self.assertIsNone(info["region"])
        self.assertIsNone(info["channel_num"])
        self.assertIsNone(info["short_name"])


class PacketSignalFromHandshakeTest(unittest.TestCase):
    def test_packet_uses_handshake_frequency_not_hardcoded_us(self):
        source = SerialCaptureSource(port="/dev/ttyUSB0")
        source._radio_info = {
            "region": "EU_868",
            "channel_num": 0,
            "bandwidth_khz": 250.0,
            "spreading_factor": 11,
            "channel_name": "",
            "modem_preset": "LONG_FAST",
            "use_preset": True,
            "frequency_offset": 0.0,
            "override_frequency": 0.0,
            "channel_table": {},
        }
        result = source._packet_to_raw_capture(
            {
                "from": 0xAABBCCDD,
                "to": 0xFFFFFFFF,
                "id": 1,
                "raw": b"\x00" * 16,
                "rxRssi": -90,
                "rxSnr": 5.0,
            }
        )
        self.assertIsNotNone(result)
        self.assertEqual(result.signal.frequency_mhz, 869.525)
        self.assertEqual(result.signal.spreading_factor, 11)
        self.assertEqual(result.signal.bandwidth_khz, 250.0)


if __name__ == "__main__":
    unittest.main()
