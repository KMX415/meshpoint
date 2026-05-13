"""Tests for TxService helpers: preset names and destination resolution."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from src.config import TransmitConfig
from src.models.packet import Protocol
from src.transmit.tx_service import (
    BROADCAST_ADDR_MC,
    BROADCAST_ADDR_MT,
    PRESET_DISPLAY_NAMES,
    RESERVED_NODE_IDS,
    TxService,
)


class TestPresetDisplayNames(unittest.TestCase):

    def test_longfast(self):
        self.assertEqual(PRESET_DISPLAY_NAMES[(11, 250)], "LongFast")

    def test_shortfast(self):
        self.assertEqual(PRESET_DISPLAY_NAMES[(7, 250)], "ShortFast")

    def test_shortturbo(self):
        self.assertEqual(PRESET_DISPLAY_NAMES[(7, 500)], "ShortTurbo")

    def test_mediumfast(self):
        self.assertEqual(PRESET_DISPLAY_NAMES[(9, 250)], "MediumFast")

    def test_longturbo(self):
        self.assertEqual(PRESET_DISPLAY_NAMES[(11, 500)], "LongTurbo")

    def test_all_presets_present(self):
        expected = {
            "ShortFast", "ShortTurbo", "ShortSlow",
            "MediumFast", "MediumSlow",
            "LongFast", "LongTurbo", "LongMod", "LongSlow", "VLongSlow",
        }
        self.assertEqual(set(PRESET_DISPLAY_NAMES.values()), expected)

    def test_custom_falls_through(self):
        self.assertNotIn((6, 125), PRESET_DISPLAY_NAMES)


class TestResolveDestination(unittest.TestCase):

    def test_broadcast_string(self):
        result = TxService._resolve_destination("broadcast", Protocol.MESHTASTIC)
        self.assertEqual(result, BROADCAST_ADDR_MT)

    def test_broadcast_all(self):
        result = TxService._resolve_destination("all", Protocol.MESHTASTIC)
        self.assertEqual(result, BROADCAST_ADDR_MT)

    def test_broadcast_hex_ff(self):
        result = TxService._resolve_destination("ffffffff", Protocol.MESHTASTIC)
        self.assertEqual(result, BROADCAST_ADDR_MT)

    def test_hex_node_id(self):
        result = TxService._resolve_destination("deadbeef", Protocol.MESHTASTIC)
        self.assertEqual(result, 0xDEADBEEF)

    def test_hex_node_id_with_bang(self):
        result = TxService._resolve_destination("!bdd391b5", Protocol.MESHTASTIC)
        self.assertEqual(result, 0xBDD391B5)

    def test_non_hex_string_falls_to_broadcast(self):
        result = TxService._resolve_destination("not-a-node", Protocol.MESHTASTIC)
        self.assertEqual(result, BROADCAST_ADDR_MT)

    def test_integer_passthrough(self):
        result = TxService._resolve_destination(0x12345678, Protocol.MESHTASTIC)
        self.assertEqual(result, 0x12345678)

    def test_broadcast_constants(self):
        self.assertEqual(BROADCAST_ADDR_MT, 0xFFFFFFFF)
        self.assertEqual(BROADCAST_ADDR_MC, 0xFFFF)


class TestResolveNodeId(unittest.TestCase):
    """``_resolve_node_id`` contract: config wins, derive next, random last."""

    def _build(self, *, node_id=None, device_id=None) -> TxService:
        cfg = TransmitConfig(enabled=True, node_id=node_id)
        return TxService(
            transmit_config=cfg,
            device_id=device_id,
            persist_derived_node_id=False,
        )

    def test_config_node_id_wins(self):
        svc = self._build(node_id=0xDEADBEEF, device_id="some-uuid")
        self.assertEqual(svc.source_node_id, 0xDEADBEEF)

    def test_derived_from_device_id_is_deterministic(self):
        device_id = "11111111-2222-3333-4444-555555555555"
        a = self._build(device_id=device_id)
        b = self._build(device_id=device_id)
        self.assertEqual(a.source_node_id, b.source_node_id)

    def test_different_device_ids_produce_different_node_ids(self):
        a = self._build(device_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
        b = self._build(device_id="bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
        self.assertNotEqual(a.source_node_id, b.source_node_id)

    def test_random_fallback_when_no_config_no_device_id(self):
        svc = self._build(node_id=None, device_id=None)
        self.assertNotIn(svc.source_node_id, RESERVED_NODE_IDS)
        self.assertGreaterEqual(svc.source_node_id, 1)
        self.assertLessEqual(svc.source_node_id, 0xFFFFFFFE)

    def test_reserved_config_value_falls_through(self):
        """A config node_id of 0 or 0xFFFFFFFF should not be honored."""
        for reserved in RESERVED_NODE_IDS:
            with self.subTest(reserved=reserved):
                svc = self._build(node_id=reserved, device_id="some-uuid")
                self.assertNotIn(svc.source_node_id, RESERVED_NODE_IDS)

    def test_derive_skips_reserved_in_first_word(self):
        """If sha256[:4] hits 0x00000000, derive must skip to next word."""
        zero = (0).to_bytes(4, "big")
        nonzero = (0x01234567).to_bytes(4, "big")
        digest = zero + nonzero + b"\x00" * 24
        with patch(
            "hashlib.sha256",
            return_value=type("D", (), {"digest": lambda self: digest})(),
        ):
            value = TxService._derive_node_id("anything")
        self.assertEqual(value, 0x01234567)

    def test_derive_skips_reserved_broadcast(self):
        """If sha256[:4] hits 0xFFFFFFFF, derive must skip to next word."""
        broadcast = (0xFFFFFFFF).to_bytes(4, "big")
        nonzero = (0x42424242).to_bytes(4, "big")
        digest = broadcast + nonzero + b"\x00" * 24
        with patch(
            "hashlib.sha256",
            return_value=type("D", (), {"digest": lambda self: digest})(),
        ):
            value = TxService._derive_node_id("anything")
        self.assertEqual(value, 0x42424242)

    def test_random_non_reserved_never_returns_reserved(self):
        for _ in range(100):
            value = TxService._random_non_reserved()
            self.assertNotIn(value, RESERVED_NODE_IDS)
            self.assertGreaterEqual(value, 0)
            self.assertLessEqual(value, 0xFFFFFFFF)


class TestNodeIdSourceTracking(unittest.TestCase):
    """``node_id_source`` reports where the resolved value came from."""

    def _build(self, *, node_id=None, device_id=None) -> TxService:
        cfg = TransmitConfig(enabled=True, node_id=node_id)
        return TxService(
            transmit_config=cfg,
            device_id=device_id,
            persist_derived_node_id=False,
        )

    def test_source_is_config_when_pinned(self):
        svc = self._build(node_id=0xDEADBEEF, device_id="some-uuid")
        self.assertEqual(svc.node_id_source, "config")

    def test_source_is_derived_when_only_device_id_set(self):
        svc = self._build(node_id=None, device_id="some-uuid")
        self.assertEqual(svc.node_id_source, "derived")

    def test_source_is_random_when_nothing_set(self):
        svc = self._build(node_id=None, device_id=None)
        self.assertEqual(svc.node_id_source, "random")

    def test_reserved_config_falls_through_to_derived(self):
        svc = self._build(node_id=0x00000000, device_id="some-uuid")
        self.assertEqual(svc.node_id_source, "derived")


class TestPersistDerivedNodeId(unittest.TestCase):
    """First boot with no pinned ID writes the derived value to local.yaml."""

    def test_derived_id_is_persisted_and_source_flips_to_config(self):
        cfg = TransmitConfig(enabled=True, node_id=None)
        with patch(
            "src.config.save_section_to_yaml"
        ) as mock_save:
            svc = TxService(
                transmit_config=cfg,
                device_id="11111111-2222-3333-4444-555555555555",
                persist_derived_node_id=True,
            )
        mock_save.assert_called_once()
        section, values = mock_save.call_args.args
        self.assertEqual(section, "transmit")
        self.assertEqual(values, {"node_id": svc.source_node_id})
        self.assertEqual(svc.node_id_source, "config")
        self.assertEqual(cfg.node_id, svc.source_node_id)

    def test_pinned_id_does_not_trigger_persist(self):
        cfg = TransmitConfig(enabled=True, node_id=0xDEADBEEF)
        with patch(
            "src.config.save_section_to_yaml"
        ) as mock_save:
            TxService(
                transmit_config=cfg,
                device_id="some-uuid",
                persist_derived_node_id=True,
            )
        mock_save.assert_not_called()

    def test_random_id_does_not_trigger_persist(self):
        cfg = TransmitConfig(enabled=True, node_id=None)
        with patch(
            "src.config.save_section_to_yaml"
        ) as mock_save:
            TxService(
                transmit_config=cfg,
                device_id=None,
                persist_derived_node_id=True,
            )
        mock_save.assert_not_called()

    def test_persist_failure_is_swallowed_and_source_stays_derived(self):
        cfg = TransmitConfig(enabled=True, node_id=None)
        with patch(
            "src.config.save_section_to_yaml",
            side_effect=PermissionError("read-only filesystem"),
        ):
            svc = TxService(
                transmit_config=cfg,
                device_id="some-uuid",
                persist_derived_node_id=True,
            )
        self.assertEqual(svc.node_id_source, "derived")
        self.assertNotEqual(svc.source_node_id, 0)


if __name__ == "__main__":
    unittest.main()
