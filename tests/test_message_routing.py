"""Tests for Meshtastic DM identity routing."""

import unittest

from src.api.message_routing import build_our_meshtastic_node_ids
from src.capture.meshtasticd_config_sync import read_local_node_id_hex


class TestBuildOurMeshtasticNodeIds(unittest.TestCase):
    def test_includes_configured_and_meshtasticd_ids(self):
        ids = build_our_meshtastic_node_ids(
            0x7E3FA19C,
            "9ea7e9d9",
        )
        self.assertEqual(ids, frozenset({"7e3fa19c", "9ea7e9d9"}))

    def test_meshtasticd_id_only(self):
        ids = build_our_meshtastic_node_ids(None, "!9ea7e9d9")
        self.assertEqual(ids, frozenset({"9ea7e9d9"}))


class TestReadLocalNodeIdHex(unittest.TestCase):
    def test_reads_node_num(self):
        class FakeLocalNode:
            nodeNum = 0x9EA7E9D9

        class FakeIface:
            localNode = FakeLocalNode()

        self.assertEqual(read_local_node_id_hex(FakeIface()), "9ea7e9d9")


if __name__ == "__main__":
    unittest.main()
