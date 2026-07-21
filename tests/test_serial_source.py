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


if __name__ == "__main__":
    unittest.main()
