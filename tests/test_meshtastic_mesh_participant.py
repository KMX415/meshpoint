"""Tests for Meshtastic mesh-participant packet builders."""

from __future__ import annotations

import unittest

from src.decode.crypto_service import CryptoService
from src.decode.meshtastic_decoder import MeshtasticDecoder
from src.identity.keypair import MeshpointKeypair
from src.transmit.meshtastic_builder import MeshtasticPacketBuilder


class TestMeshtasticMeshParticipantBuilder(unittest.TestCase):
    def setUp(self):
        self.crypto = CryptoService()
        self.builder = MeshtasticPacketBuilder(self.crypto)
        self.decoder = MeshtasticDecoder(self.crypto)
        self.keypair = MeshpointKeypair.generate()
        self.crypto.set_keypair(self.keypair.private_key, self.keypair.public_key)
        self.source_id = 0xDEADBEEF
        self.dest_id = 0xCAFEBABE

    def test_nodeinfo_includes_public_key(self):
        packet = self.builder.build_nodeinfo(
            source_id=self.source_id,
            packet_id=1,
            long_name="Meshpoint",
            short_name="MPNT",
            public_key=self.keypair.public_key,
        )
        self.assertIsNotNone(packet)
        decoded = self.decoder.decode(packet)
        self.assertIsNotNone(decoded)
        assert decoded is not None
        self.assertTrue(decoded.decrypted)
        self.assertEqual(decoded.decoded_payload.get("public_key"), self.keypair.public_key.hex())

    def test_routing_ack_carries_request_id(self):
        request_id = 0x00ABCDEF
        packet = self.builder.build_routing_ack(
            source_id=self.source_id,
            dest=self.dest_id,
            packet_id=2,
            request_id=request_id,
        )
        self.assertIsNotNone(packet)
        decoded = self.decoder.decode(packet)
        assert decoded is not None
        self.assertEqual(decoded.decoded_payload.get("request_id"), request_id)

    def test_pki_text_round_trip(self):
        peer = MeshpointKeypair.generate()
        self.crypto.register_public_key(self.dest_id, peer.public_key)
        self.decoder.configure_identity(self.dest_id)

        packet = self.builder.build_text_message(
            text="pki dm",
            dest=self.dest_id,
            source_id=self.source_id,
            packet_id=3,
            recipient_public_key=peer.public_key,
        )
        assert packet is not None
        self.assertEqual(packet[13], 0)
        peer_crypto = CryptoService()
        peer_crypto.set_keypair(peer.private_key, peer.public_key)
        peer_crypto.register_public_key(self.source_id, self.keypair.public_key)
        peer_decoder = MeshtasticDecoder(peer_crypto)
        peer_decoder.configure_identity(self.dest_id)
        decoded = peer_decoder.decode(packet)
        assert decoded is not None
        self.assertEqual(decoded.decoded_payload.get("text"), "pki dm")


if __name__ == "__main__":
    unittest.main()
