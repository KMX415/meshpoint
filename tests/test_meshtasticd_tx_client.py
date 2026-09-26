"""Tests for meshtasticd TX client destination mapping."""

import unittest

from src.transmit.meshtasticd_tx_client import MeshtasticdTxClient
from src.transmit.tx_service import BROADCAST_ADDR_MT


class TestMeshtasticdTxDestination(unittest.TestCase):
    def test_broadcast_string(self):
        dest = MeshtasticdTxClient._format_destination("broadcast")
        self.assertEqual(dest, BROADCAST_ADDR_MT)

    def test_broadcast_conversation_key(self):
        dest = MeshtasticdTxClient._format_destination("broadcast:meshtastic:0")
        self.assertEqual(dest, BROADCAST_ADDR_MT)

    def test_hex_node_id_with_bang(self):
        dest = MeshtasticdTxClient._format_destination("!bdd391b5")
        self.assertEqual(dest, 0xBDD391B5)

    def test_bare_hex_node_id(self):
        dest = MeshtasticdTxClient._format_destination("bdd391b5")
        self.assertEqual(dest, 0xBDD391B5)


if __name__ == "__main__":
    unittest.main()
