"""Tests for ChannelResolver (MQTT channel hash -> name mapping).

Verifies that all standard Meshtastic presets resolve to their correct
channel name, and that user-configured channel keys extend the lookup.
Covers the fix for GitHub issue #20.
"""

from __future__ import annotations

import unittest

from src.models.packet import Protocol
from src.relay.channel_resolver import (
    ChannelResolver,
    STANDARD_PRESETS,
    _expand_key,
    _xor_hash,
)


class TestDefaultPresetResolution(unittest.TestCase):
    """Standard presets with default PSK resolve to correct names."""

    def setUp(self):
        self.resolver = ChannelResolver()

    def test_longfast_hash_8(self):
        self.assertEqual(
            self.resolver.resolve(8, Protocol.MESHTASTIC), "LongFast"
        )

    def test_longfast_hash_0(self):
        self.assertEqual(
            self.resolver.resolve(0, Protocol.MESHTASTIC), "LongFast"
        )

    def test_longturbo_hash_118(self):
        self.assertEqual(
            self.resolver.resolve(118, Protocol.MESHTASTIC), "LongTurbo"
        )

    def test_mediumfast(self):
        self.assertEqual(
            self.resolver.resolve(31, Protocol.MESHTASTIC), "MediumFast"
        )

    def test_mediumslow(self):
        self.assertEqual(
            self.resolver.resolve(24, Protocol.MESHTASTIC), "MediumSlow"
        )

    def test_longslow(self):
        self.assertEqual(
            self.resolver.resolve(15, Protocol.MESHTASTIC), "LongSlow"
        )

    def test_longmoderate(self):
        self.assertEqual(
            self.resolver.resolve(9, Protocol.MESHTASTIC), "LongModerate"
        )

    def test_shortfast(self):
        self.assertEqual(
            self.resolver.resolve(112, Protocol.MESHTASTIC), "ShortFast"
        )

    def test_shortslow(self):
        self.assertEqual(
            self.resolver.resolve(119, Protocol.MESHTASTIC), "ShortSlow"
        )

    def test_shortturbo(self):
        self.assertEqual(
            self.resolver.resolve(14, Protocol.MESHTASTIC), "ShortTurbo"
        )

    def test_all_presets_unique_hashes(self):
        hashes = set()
        for name in STANDARD_PRESETS:
            h = next(
                k for k, v in self.resolver._hash_to_name.items()
                if v == name
            )
            self.assertNotIn(h, hashes, f"Duplicate hash for {name}")
            hashes.add(h)

    def test_unknown_hash_falls_back(self):
        self.assertEqual(
            self.resolver.resolve(200, Protocol.MESHTASTIC), "ch200"
        )


class TestMeshCoreProtocol(unittest.TestCase):
    """MeshCore protocol always resolves to 'MeshCore'."""

    def setUp(self):
        self.resolver = ChannelResolver()

    def test_meshcore_ignores_hash(self):
        self.assertEqual(
            self.resolver.resolve(31, Protocol.MESHCORE), "MeshCore"
        )

    def test_meshcore_hash_zero(self):
        self.assertEqual(
            self.resolver.resolve(0, Protocol.MESHCORE), "MeshCore"
        )


class TestUserChannelKeys(unittest.TestCase):
    """User-configured channel keys extend the lookup table."""

    def test_custom_channel_resolves(self):
        full_key_b64 = "1PG7OiApB1nwvP+rz05pAQ=="
        resolver = ChannelResolver(
            channel_keys={"MyPrivate": full_key_b64}
        )
        import base64
        expanded = _expand_key(base64.b64decode(full_key_b64))
        expected_hash = _xor_hash("MyPrivate", expanded)
        self.assertEqual(
            resolver.resolve(expected_hash, Protocol.MESHTASTIC),
            "MyPrivate",
        )

    def test_invalid_key_skipped(self):
        resolver = ChannelResolver(
            channel_keys={"BadKey": "not-valid-base64!!!"}
        )
        self.assertEqual(
            resolver.resolve(8, Protocol.MESHTASTIC), "LongFast"
        )


class TestIsKnown(unittest.TestCase):

    def setUp(self):
        self.resolver = ChannelResolver()

    def test_known_preset(self):
        self.assertTrue(self.resolver.is_known(8))

    def test_hash_zero_known(self):
        self.assertTrue(self.resolver.is_known(0))

    def test_unknown_hash(self):
        self.assertFalse(self.resolver.is_known(200))


class TestGate2WithResolver(unittest.TestCase):
    """Verify that gate 2 allowlist works with resolved names."""

    def test_mediumfast_passes_when_allowed(self):
        resolver = ChannelResolver()
        allowed = {"longfast", "mediumfast", "meshcore"}
        name = resolver.resolve(31, Protocol.MESHTASTIC)
        self.assertIn(name.lower(), allowed)

    def test_mediumfast_blocked_when_not_allowed(self):
        resolver = ChannelResolver()
        allowed = {"longfast", "meshcore"}
        name = resolver.resolve(31, Protocol.MESHTASTIC)
        self.assertNotIn(name.lower(), allowed)

    def test_longturbo_is_distinct_from_longfast_allowlist(self):
        resolver = ChannelResolver()
        name = resolver.resolve(118, Protocol.MESHTASTIC)
        self.assertNotIn(name.lower(), {"longfast", "meshcore"})
        self.assertIn(name.lower(), {"longturbo", "meshcore"})


if __name__ == "__main__":
    unittest.main()
