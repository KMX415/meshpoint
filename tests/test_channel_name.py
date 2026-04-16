"""Tests for primary channel name configuration and hash computation.

Verifies that the Meshpoint uses the configured channel name (not the
modem preset name) when computing the Meshtastic channel hash. Covers
the fix for GitHub issue #13.
"""

from __future__ import annotations

import base64
import unittest
from unittest.mock import MagicMock, patch

from src.config import MeshtasticConfig, RadioConfig
from src.transmit.tx_service import PRESET_DISPLAY_NAMES, TxService


MESHTASTIC_DEFAULT_PSK = bytes([
    0xD4, 0xF1, 0xBB, 0x3A, 0x20, 0x29, 0x07, 0x59,
    0xF0, 0xBC, 0xFF, 0xAB, 0xCF, 0x4E, 0x69, 0x01,
])


def _expand_key(raw_key: bytes) -> bytes:
    if len(raw_key) == 0:
        return b"\x00" * 16
    if len(raw_key) in (16, 32):
        return raw_key
    if len(raw_key) == 1:
        index = raw_key[0]
        if index == 0:
            return b"\x00" * 16
        key = bytearray(MESHTASTIC_DEFAULT_PSK)
        key[-1] = (key[-1] + index - 1) & 0xFF
        return bytes(key)
    return (raw_key + b"\x00" * 16)[:16]


def _compute_channel_hash(channel_name: str, expanded_key: bytes) -> int:
    h = 0
    for b in channel_name.encode():
        h ^= b
    for b in expanded_key:
        h ^= b
    return h


class TestChannelHashDifference(unittest.TestCase):
    """Blank and preset channel names must produce different hashes."""

    def setUp(self):
        raw_key = base64.b64decode("AQ==")
        self.expanded = _expand_key(raw_key)

    def test_blank_vs_longfast(self):
        blank_hash = _compute_channel_hash("", self.expanded)
        lf_hash = _compute_channel_hash("LongFast", self.expanded)
        self.assertNotEqual(blank_hash, lf_hash)

    def test_blank_vs_mediumfast(self):
        blank_hash = _compute_channel_hash("", self.expanded)
        mf_hash = _compute_channel_hash("MediumFast", self.expanded)
        self.assertNotEqual(blank_hash, mf_hash)

    def test_blank_name_is_deterministic(self):
        h1 = _compute_channel_hash("", self.expanded)
        h2 = _compute_channel_hash("", self.expanded)
        self.assertEqual(h1, h2)

    def test_each_preset_produces_unique_hash(self):
        hashes = set()
        for name in PRESET_DISPLAY_NAMES.values():
            h = _compute_channel_hash(name, self.expanded)
            hashes.add(h)
        blank = _compute_channel_hash("", self.expanded)
        hashes.add(blank)
        self.assertEqual(len(hashes), len(PRESET_DISPLAY_NAMES) + 1)


class TestMeshtasticConfigDefault(unittest.TestCase):
    """MeshtasticConfig defaults to LongFast primary channel name."""

    def test_default_is_longfast(self):
        cfg = MeshtasticConfig()
        self.assertEqual(cfg.primary_channel_name, "LongFast")

    def test_custom_name_preserved(self):
        cfg = MeshtasticConfig(primary_channel_name="BayMesh")
        self.assertEqual(cfg.primary_channel_name, "BayMesh")


class TestTxServicePrimaryChannelName(unittest.TestCase):
    """TxService._resolve_channel uses primary_channel_name, not preset."""

    def _make_crypto(self, default_key_b64: str = "AQ=="):
        raw = base64.b64decode(default_key_b64)
        expanded = _expand_key(raw)

        crypto = MagicMock()
        crypto.get_all_keys.return_value = [expanded]
        crypto._keys = {}
        crypto.compute_channel_hash.side_effect = _compute_channel_hash
        return crypto, expanded

    def test_blank_name_hashes_blank(self):
        crypto, expanded = self._make_crypto()
        svc = TxService(crypto=crypto, primary_channel_name="")
        h, _ = svc._resolve_channel(0)
        expected = _compute_channel_hash("", expanded)
        self.assertEqual(h, expected)

    def test_longfast_default_produces_0x08(self):
        crypto, expanded = self._make_crypto()
        svc = TxService(crypto=crypto, primary_channel_name="LongFast")
        h, _ = svc._resolve_channel(0)
        self.assertEqual(h, 0x08)

    def test_custom_name_hash(self):
        crypto, expanded = self._make_crypto()
        svc = TxService(crypto=crypto, primary_channel_name="BayMesh")
        h, _ = svc._resolve_channel(0)
        expected = _compute_channel_hash("BayMesh", expanded)
        self.assertEqual(h, expected)


class TestBuildChannelList(unittest.TestCase):
    """_build_channel_list uses primary_channel_name for hash."""

    def test_blank_name_derives_from_preset(self):
        from src.api.routes.config_routes import _build_channel_list

        mt = MeshtasticConfig(primary_channel_name="")

        with patch("src.api.routes.config_routes._config") as mock_cfg:
            mock_cfg.meshtastic = mt
            mock_cfg.radio = RadioConfig(
                spreading_factor=9, bandwidth_khz=250,
            )
            with patch("src.api.routes.config_routes._crypto", None):
                channels = _build_channel_list(mt)

        ch0 = channels[0]
        self.assertEqual(ch0["name"], "MediumFast")
        self.assertEqual(ch0["hash_name"], "MediumFast")

    def test_custom_name_used_directly(self):
        from src.api.routes.config_routes import _build_channel_list

        mt = MeshtasticConfig(primary_channel_name="BayMesh")

        with patch("src.api.routes.config_routes._config") as mock_cfg:
            mock_cfg.meshtastic = mt
            mock_cfg.radio = RadioConfig()
            with patch("src.api.routes.config_routes._crypto", None):
                channels = _build_channel_list(mt)

        ch0 = channels[0]
        self.assertEqual(ch0["name"], "BayMesh")
        self.assertEqual(ch0["hash_name"], "BayMesh")


if __name__ == "__main__":
    unittest.main()
