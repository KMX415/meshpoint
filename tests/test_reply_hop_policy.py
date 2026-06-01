"""Tests for Meshtastic reply hop mirroring."""

from __future__ import annotations

import unittest

from src.transmit.reply_hop_policy import MeshtasticReplyHopPolicy


class TestMeshtasticReplyHopPolicy(unittest.TestCase):
    def test_direct_three_hop_request_gets_two_hop_reply(self):
        limit = MeshtasticReplyHopPolicy.hop_limit_for_response(3, 3, 3)
        self.assertEqual(limit, 2)

    def test_zero_hop_request_gets_zero_hop_reply(self):
        limit = MeshtasticReplyHopPolicy.hop_limit_for_response(0, 0, 3)
        self.assertEqual(limit, 0)

    def test_relayed_request_uses_hops_used_plus_margin_when_room(self):
        limit = MeshtasticReplyHopPolicy.hop_limit_for_response(2, 3, 5)
        self.assertEqual(limit, 3)

    def test_excessive_hops_used_matches_request(self):
        limit = MeshtasticReplyHopPolicy.hop_limit_for_response(0, 7, 3)
        self.assertEqual(limit, 7)

    def test_invalid_header_falls_back_to_configured(self):
        limit = MeshtasticReplyHopPolicy.hop_limit_for_response(5, 2, 3)
        self.assertEqual(limit, 3)

    def test_reply_hop_fields_sets_start_equal_to_limit(self):
        hop_limit, hop_start = MeshtasticReplyHopPolicy.reply_hop_fields(0, 0, 3)
        self.assertEqual(hop_limit, 0)
        self.assertEqual(hop_start, 0)


if __name__ == "__main__":
    unittest.main()
