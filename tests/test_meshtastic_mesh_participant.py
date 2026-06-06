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

    def test_traceroute_reply_carries_request_id(self):
        request_id = 0x11223344
        packet = self.builder.build_traceroute_reply(
            source_id=self.source_id,
            dest=self.dest_id,
            packet_id=5,
            route_nodes=[],
            request_id=request_id,
            snr_towards=[30],
            route_back=[self.dest_id],
            snr_back=[30],
        )
        self.assertIsNotNone(packet)
        decoded = self.decoder.decode(packet)
        assert decoded is not None
        self.assertEqual(decoded.packet_type.value, "traceroute")
        self.assertEqual(decoded.decoded_payload.get("request_id"), request_id)
        self.assertEqual(decoded.decoded_payload.get("snr_back"), [30])

    def test_traceroute_reply_preserves_inbound_hops(self):
        from src.models.packet import Packet, PacketType, Protocol
        from src.transmit.tx_service import TxService

        original = Packet(
            packet_id="66d7046c",
            source_id="7d8b98a9",
            destination_id="c0ffee42",
            protocol=Protocol.MESHTASTIC,
            packet_type=PacketType.TRACEROUTE,
            decrypted=True,
            decoded_payload={
                "route": ["11223344", "55667788"],
                "snr_towards": [16, 20],
            },
        )
        route, snr_t, route_back, snr_b = TxService._build_traceroute_reply_data(
            original, 7.5
        )
        self.assertEqual(route, [0x11223344, 0x55667788])
        self.assertEqual(snr_t, [16, 20, 30])
        self.assertEqual(route_back, [0x7D8B98A9])
        self.assertEqual(snr_b, [30])

    def test_pki_traceroute_reply_round_trip(self):
        peer = MeshpointKeypair.generate()
        self.crypto.register_public_key(self.dest_id, peer.public_key)
        request_id = 0x55667788
        packet = self.builder.build_traceroute_reply(
            source_id=self.source_id,
            dest=self.dest_id,
            packet_id=6,
            route_nodes=[],
            request_id=request_id,
            snr_towards=[28],
            route_back=[self.dest_id],
            snr_back=[28],
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
        self.assertTrue(decoded.decrypted)
        self.assertEqual(decoded.decoded_payload.get("request_id"), request_id)
        self.assertEqual(decoded.decoded_payload.get("snr_back"), [28])

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

    def test_telemetry_reply_carries_request_id(self):
        request_id = 0xAABBCCDD
        packet = self.builder.build_telemetry_reply(
            source_id=self.source_id,
            dest=self.dest_id,
            packet_id=7,
            request_id=request_id,
            variant="local_stats",
            uptime_seconds=3600,
            num_packets_rx=42,
            noise_floor=-95,
            telemetry_time=1_700_000_000,
        )
        self.assertIsNotNone(packet)
        decoded = self.decoder.decode(packet)
        assert decoded is not None
        self.assertEqual(decoded.decoded_payload.get("request_id"), request_id)
        self.assertEqual(decoded.decoded_payload.get("telemetry_variant"), "local_stats")
        self.assertEqual(decoded.decoded_payload.get("num_packets_rx"), 42)

    def test_pki_telemetry_reply_round_trip(self):
        peer = MeshpointKeypair.generate()
        self.crypto.register_public_key(self.dest_id, peer.public_key)
        request_id = 0x66D70477
        packet = self.builder.build_telemetry_reply(
            source_id=self.source_id,
            dest=self.dest_id,
            packet_id=0x0000DAB6,
            request_id=request_id,
            variant="local_stats",
            uptime_seconds=3600,
            num_packets_rx=42,
            noise_floor=-95,
            telemetry_time=1_700_000_000,
            channel_hash=0,
            recipient_public_key=peer.public_key,
            hop_limit=2,
            hop_start=2,
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
        self.assertTrue(decoded.decrypted)
        self.assertEqual(decoded.decoded_payload.get("request_id"), request_id)
        self.assertEqual(
            decoded.decoded_payload.get("telemetry_variant"), "local_stats"
        )
        self.assertEqual(decoded.decoded_payload.get("num_packets_rx"), 42)

    def test_telemetry_reply_hop_mirrors_zero_hop_request(self):
        from src.models.packet import Packet, PacketType, Protocol
        from src.transmit.reply_hop_policy import MeshtasticReplyHopPolicy

        original = Packet(
            packet_id="66d70477",
            source_id="7d8b98a9",
            destination_id="c0ffee42",
            protocol=Protocol.MESHTASTIC,
            packet_type=PacketType.TELEMETRY,
            decrypted=True,
            hop_limit=0,
            hop_start=0,
            channel_hash=0,
            decoded_payload={"telemetry_variant": "local_stats"},
        )
        hop_limit, hop_start = MeshtasticReplyHopPolicy.reply_hop_fields(
            original.hop_limit, original.hop_start, 3
        )
        self.assertEqual(hop_limit, 0)
        self.assertEqual(hop_start, 0)

    def test_channel_request_uses_channel_encryption_even_with_pubkey(self):
        peer = MeshpointKeypair.generate()
        self.crypto.register_public_key(self.dest_id, peer.public_key)
        packet = self.builder.build_traceroute_reply(
            source_id=self.source_id,
            dest=self.dest_id,
            packet_id=8,
            route_nodes=[],
            request_id=0x12345678,
            channel_hash=0x08,
            recipient_public_key=None,
        )
        assert packet is not None
        self.assertEqual(packet[13], 0x08)


if __name__ == "__main__":
    unittest.main()
