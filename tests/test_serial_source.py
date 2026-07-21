"""Serial capture: self-origin filter (javastraat A1 rewrite)."""

from __future__ import annotations

import unittest
from types import SimpleNamespace

from src.capture.serial_source import SerialCaptureSource, SerialSelfOriginFilter


class SerialSelfOriginFilterTest(unittest.TestCase):
    """Stick self-telemetry/nodeinfo must drop; own text must pass."""

    def test_telemetry_from_own_node_is_dropped(self):
        filt = SerialSelfOriginFilter(own_node_num=0x09D406F4)
        self.assertTrue(
            filt.should_drop(
                {
                    "from": 0x09D406F4,
                    "to": 0xFFFFFFFF,
                    "decoded": {"portnum": "TELEMETRY_APP", "payload": ""},
                }
            )
        )

    def test_nodeinfo_from_own_node_is_dropped(self):
        filt = SerialSelfOriginFilter(own_node_num=0x09D406F4)
        self.assertTrue(
            filt.should_drop(
                {
                    "from": 0x09D406F4,
                    "decoded": {"portnum": "NODEINFO_APP"},
                }
            )
        )

    def test_self_originated_text_message_is_not_dropped(self):
        filt = SerialSelfOriginFilter(own_node_num=0x09D406F4)
        self.assertFalse(
            filt.should_drop(
                {
                    "from": 0x09D406F4,
                    "to": 0xFFFFFFFF,
                    "decoded": {"portnum": "TEXT_MESSAGE_APP", "payload": ""},
                }
            )
        )

    def test_text_portnum_numeric_is_not_dropped(self):
        filt = SerialSelfOriginFilter(own_node_num=0x09D406F4)
        self.assertFalse(
            filt.should_drop(
                {
                    "from": 0x09D406F4,
                    "decoded": {"portnum": 1},
                }
            )
        )

    def test_packet_from_remote_node_is_not_dropped(self):
        filt = SerialSelfOriginFilter(own_node_num=0x09D406F4)
        self.assertFalse(
            filt.should_drop({"from": 0xAABBCCDD, "raw": "aabb"})
        )

    def test_unknown_own_node_num_does_not_drop(self):
        filt = SerialSelfOriginFilter(own_node_num=None)
        self.assertFalse(
            filt.should_drop(
                {
                    "from": 0x09D406F4,
                    "decoded": {"portnum": "TELEMETRY_APP"},
                }
            )
        )

    def test_missing_from_field_does_not_drop(self):
        filt = SerialSelfOriginFilter(own_node_num=0x09D406F4)
        self.assertFalse(filt.should_drop({"raw": "aabbccddeeff"}))

    def test_read_own_node_num_from_interface(self):
        iface = SimpleNamespace(myInfo=SimpleNamespace(my_node_num=0xDEADBEEF))
        self.assertEqual(
            SerialSelfOriginFilter.read_own_node_num(iface),
            0xDEADBEEF,
        )

    def test_read_own_node_num_missing_returns_none(self):
        self.assertIsNone(SerialSelfOriginFilter.read_own_node_num(object()))


class SerialCaptureSourceDropTest(unittest.TestCase):
    """End-to-end: filter wired into ``_packet_to_raw_capture``."""

    def test_own_telemetry_returns_none(self):
        source = SerialCaptureSource(port="/dev/ttyUSB0")
        source._self_origin.set_own_node_num(0x09D406F4)
        result = source._packet_to_raw_capture(
            {
                "from": 0x09D406F4,
                "to": 0xFFFFFFFF,
                "decoded": {"portnum": "TELEMETRY_APP", "payload": ""},
                "raw": "aabbccddeeff",
            }
        )
        self.assertIsNone(result)

    def test_own_text_returns_raw_capture(self):
        source = SerialCaptureSource(port="/dev/ttyUSB0")
        source._self_origin.set_own_node_num(0x09D406F4)
        result = source._packet_to_raw_capture(
            {
                "from": 0x09D406F4,
                "to": 0xFFFFFFFF,
                "raw": "aabbccddeeff",
                "decoded": {"portnum": "TEXT_MESSAGE_APP", "payload": ""},
            }
        )
        self.assertIsNotNone(result)
        self.assertEqual(result.capture_source, "serial")

    def test_remote_packet_returns_raw_capture(self):
        source = SerialCaptureSource(port="/dev/ttyUSB0")
        source._self_origin.set_own_node_num(0x09D406F4)
        result = source._packet_to_raw_capture(
            {
                "from": 0xAABBCCDD,
                "to": 0xFFFFFFFF,
                "raw": "aabbccddeeff",
            }
        )
        self.assertIsNotNone(result)


class BuildPreDecodedEarlyExitTest(unittest.TestCase):
    """Early exits that must not require the meshtastic package."""

    def setUp(self):
        self.source = SerialCaptureSource(port="/dev/ttyUSB0")

    def test_no_decoded_key_returns_none(self):
        self.assertIsNone(self.source._build_pre_decoded({"raw": "aa"}))

    def test_decoded_not_a_dict_returns_none(self):
        self.assertIsNone(
            self.source._build_pre_decoded({"decoded": "not-a-dict"})
        )

    def test_decoded_missing_portnum_returns_none(self):
        self.assertIsNone(
            self.source._build_pre_decoded({"decoded": {"payload": "AQI="}})
        )

    def test_resolves_channel_index_to_name_via_channel_table(self):
        self.source._radio_info["channel_table"] = {0: "LongFast", 2: "PD2EMC"}
        pre = self.source._build_pre_decoded(
            {
                "decoded": {"portnum": 1, "payload": ""},
                "channel": 2,
            }
        )
        self.assertEqual(pre["channel_name"], "PD2EMC")

    def test_unresolvable_channel_index_omits_channel_name(self):
        self.source._radio_info["channel_table"] = {0: "LongFast"}
        pre = self.source._build_pre_decoded(
            {
                "decoded": {"portnum": 1, "payload": ""},
                "channel": 5,
            }
        )
        self.assertIsNotNone(pre)
        self.assertNotIn("channel_name", pre)


class ReadChannelTableTest(unittest.TestCase):
    def _channel(self, index, role, name):
        from unittest.mock import MagicMock

        ch = MagicMock()
        ch.index = index
        ch.role = role
        ch.settings.name = name
        return ch

    def test_builds_index_to_name_map_skipping_disabled(self):
        from meshtastic.protobuf import channel_pb2
        from unittest.mock import MagicMock

        R = channel_pb2.Channel.Role
        channels = [
            self._channel(0, R.PRIMARY, "Home"),
            self._channel(1, R.SECONDARY, "BayMesh"),
            self._channel(2, R.DISABLED, "Unused"),
        ]
        iface = MagicMock()
        iface.localNode.channels = channels

        table = SerialCaptureSource._read_channel_table(
            iface, modem_preset_name="LongFast"
        )
        self.assertEqual(table, {0: "Home", 1: "BayMesh"})

    def test_blank_primary_name_falls_back_to_modem_preset(self):
        from meshtastic.protobuf import channel_pb2
        from unittest.mock import MagicMock

        R = channel_pb2.Channel.Role
        channels = [self._channel(0, R.PRIMARY, "")]
        iface = MagicMock()
        iface.localNode.channels = channels

        table = SerialCaptureSource._read_channel_table(
            iface, modem_preset_name="LongFast"
        )
        self.assertEqual(table, {0: "LongFast"})

    def test_blank_secondary_name_is_skipped_not_guessed(self):
        from meshtastic.protobuf import channel_pb2
        from unittest.mock import MagicMock

        R = channel_pb2.Channel.Role
        channels = [
            self._channel(0, R.PRIMARY, "Home"),
            self._channel(1, R.SECONDARY, ""),
        ]
        iface = MagicMock()
        iface.localNode.channels = channels

        table = SerialCaptureSource._read_channel_table(
            iface, modem_preset_name="LongFast"
        )
        self.assertEqual(table, {0: "Home"})


class ResolveChannelIndexTest(unittest.TestCase):
    def test_finds_index_for_known_name(self):
        source = SerialCaptureSource(port="/dev/ttyUSB1")
        source._radio_info["channel_table"] = {0: "LongFast", 2: "PD2EMC"}
        self.assertEqual(source.resolve_channel_index("PD2EMC"), 2)

    def test_returns_none_for_unknown_name(self):
        source = SerialCaptureSource(port="/dev/ttyUSB1")
        source._radio_info["channel_table"] = {0: "LongFast"}
        self.assertIsNone(source.resolve_channel_index("SomeOtherChannel"))

    def test_returns_none_when_channel_table_never_populated(self):
        source = SerialCaptureSource(port="/dev/ttyUSB1")
        self.assertIsNone(source.resolve_channel_index("LongFast"))


class ReconstructRawTest(unittest.TestCase):
    """MeshPacket raw is a protobuf object; encrypted is base64."""

    def test_protobuf_raw_object_triggers_reconstruction(self):
        source = SerialCaptureSource(port="/dev/ttyUSB0")
        result = source._packet_to_raw_capture(
            {
                "from": 0xAABBCCDD,
                "to": 0xFFFFFFFF,
                "id": 1,
                "raw": object(),  # MeshPacket stand-in
                "encrypted": "",
            }
        )
        self.assertIsNotNone(result)
        self.assertGreaterEqual(len(result.payload), 16)

    def test_encrypted_base64_appended_to_header(self):
        import base64

        source = SerialCaptureSource(port="/dev/ttyUSB0")
        body = base64.b64encode(b"\x01\x02\x03").decode()
        result = source._packet_to_raw_capture(
            {
                "from": 0xAABBCCDD,
                "to": 0xFFFFFFFF,
                "id": 1,
                "raw": object(),
                "encrypted": body,
            }
        )
        self.assertIsNotNone(result)
        self.assertEqual(result.payload[16:], b"\x01\x02\x03")


if __name__ == "__main__":
    unittest.main()
