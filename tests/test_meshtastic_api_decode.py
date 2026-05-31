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


if __name__ == "__main__":
    unittest.main()
