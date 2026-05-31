"""Tests for meshtastic API packet decode path."""

import unittest

from src.decode.crypto_service import CryptoService
from src.decode.meshtastic_decoder import MeshtasticDecoder
from src.models.packet import PacketType


class TestMeshtasticApiDecode(unittest.TestCase):
    def setUp(self):
        self.decoder = MeshtasticDecoder(CryptoService("AQ=="))

    def test_decode_text_from_api_dict(self):
        packet = {
            "from": 0xAABBCCDD,
            "to": 0xFFFFFFFF,
            "id": 0x01020304,
            "hopLimit": 3,
            "hopStart": 3,
            "channel": 8,
            "decoded": {
                "portnum": "TEXT_MESSAGE_APP",
                "text": "hello mesh",
            },
        }
        result = self.decoder.decode_from_api_packet(packet)
        self.assertIsNotNone(result)
        assert result is not None
        self.assertTrue(result.decrypted)
        self.assertEqual(result.packet_type, PacketType.TEXT)
        self.assertEqual(result.source_id, "aabbccdd")
        self.assertEqual(result.decoded_payload.get("text"), "hello mesh")

    def test_decode_nodeinfo_from_api_user_block(self):
        packet = {
            "from": 0x9EA7E9D9,
            "to": 0xFFFFFFFF,
            "id": 0x01020304,
            "hopLimit": 3,
            "hopStart": 3,
            "channel": 0,
            "decoded": {
                "portnum": "NODEINFO_APP",
                "payload": b"",
                "user": {
                    "longName": "Mesh Node",
                    "shortName": "MNOD",
                    "hwModel": "PORTDUINO",
                },
            },
        }
        result = self.decoder.decode_from_api_packet(packet)
        self.assertIsNotNone(result)
        assert result is not None
        self.assertTrue(result.decrypted)
        self.assertEqual(result.packet_type, PacketType.NODEINFO)
        self.assertEqual(result.source_id, "9ea7e9d9")
        self.assertEqual(result.decoded_payload.get("long_name"), "Mesh Node")


if __name__ == "__main__":
    unittest.main()
