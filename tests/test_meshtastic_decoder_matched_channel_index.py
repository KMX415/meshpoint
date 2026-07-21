"""``MeshtasticDecoder.decode()`` records which configured key decrypted
a packet, even when its on-air channel_hash doesn't match any locally
computed name+key hash.
"""

from __future__ import annotations

import struct
import unittest

from src.decode.meshtastic_decoder import MeshtasticDecoder
from src.models.packet import PacketType


def _build_header(
    *,
    channel_hash: int,
    dest_id: int = 0xFFFFFFFF,
    source_id: int = 0xDEADBEEF,
    packet_id: int = 0x12345678,
) -> bytes:
    flags = (3 & 0x07) | ((3 & 0x07) << 5)  # hop_limit=3, hop_start=3
    return (
        struct.pack("<III", dest_id, source_id, packet_id)
        + bytes([flags, channel_hash, 0x00, 0x00])
    )


class _FakeCrypto:
    """Duck-types CryptoService methods the brute-force loop uses."""

    def __init__(self, keys: list[bytes]) -> None:
        self._keys = keys

    def get_all_keys(self) -> list[bytes]:
        return list(self._keys)

    def decrypt_meshtastic(self, encrypted_payload, packet_id, source_id, key=None):
        return b"DECRYPTED:" + key


class TestMatchedChannelIndex(unittest.TestCase):
    def _decoder_with_payload_matcher(self, crypto, valid_marker: bytes):
        decoder = MeshtasticDecoder(crypto)

        def fake_decode_payload(self, decrypted):
            if decrypted == valid_marker:
                return ({"text": "hi"}, PacketType.TEXT, None, 0)
            return (None, PacketType.UNKNOWN, None, 0)

        decoder._decode_payload = fake_decode_payload.__get__(decoder)
        return decoder

    def test_second_configured_key_records_index_1(self):
        crypto = _FakeCrypto([b"primary-key", b"baymesh-key", b"third-key"])
        decoder = self._decoder_with_payload_matcher(
            crypto, valid_marker=b"DECRYPTED:baymesh-key"
        )
        raw = _build_header(channel_hash=0x6E) + b"ciphertext-body"

        packet = decoder.decode(raw)

        self.assertIsNotNone(packet)
        self.assertTrue(packet.decrypted)
        self.assertEqual(packet.matched_channel_index, 1)

    def test_primary_key_records_index_0(self):
        crypto = _FakeCrypto([b"primary-key", b"baymesh-key"])
        decoder = self._decoder_with_payload_matcher(
            crypto, valid_marker=b"DECRYPTED:primary-key"
        )
        raw = _build_header(channel_hash=0x08) + b"ciphertext-body"

        packet = decoder.decode(raw)

        self.assertIsNotNone(packet)
        self.assertEqual(packet.matched_channel_index, 0)

    def test_no_key_matches_leaves_index_none(self):
        crypto = _FakeCrypto([b"primary-key", b"baymesh-key"])
        decoder = self._decoder_with_payload_matcher(
            crypto, valid_marker=b"DECRYPTED:nothing-will-match-this"
        )
        raw = _build_header(channel_hash=0xAB) + b"ciphertext-body"

        packet = decoder.decode(raw)

        self.assertIsNotNone(packet)
        self.assertFalse(packet.decrypted)
        self.assertIsNone(packet.matched_channel_index)


if __name__ == "__main__":
    unittest.main()
