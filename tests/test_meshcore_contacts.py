"""Tests for MeshcoreContactParser (get_contacts soft-fail paths)."""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from src.transmit.meshcore_contacts import (
    MeshcoreContactCache,
    MeshcoreContactParser,
)


class TestMeshcoreContactParser(unittest.TestCase):

    def test_none_result_returns_empty(self):
        self.assertEqual(
            MeshcoreContactParser.from_command_result(None),
            [],
        )

    def test_error_event_returns_empty(self):
        fake_event_type = MagicMock()
        fake_event_type.ERROR = "ERROR"
        result = SimpleNamespace(
            type=fake_event_type.ERROR,
            payload={"reason": "no_event_received"},
        )
        with patch.dict(
            "sys.modules",
            {"meshcore": MagicMock(EventType=fake_event_type)},
        ):
            # Re-import path uses meshcore inside _is_error_event
            with patch(
                "src.transmit.meshcore_contacts.MeshcoreContactParser."
                "_is_error_event",
                return_value=True,
            ):
                self.assertEqual(
                    MeshcoreContactParser.from_command_result(result),
                    [],
                )

    def test_valid_payload_parses_contacts(self):
        result = SimpleNamespace(
            payload={
                "aabb0011223344": {
                    "adv_name": "Alice",
                    "public_key": "aabb0011223344",
                    "lastmod": 9,
                },
            },
        )
        with patch(
            "src.transmit.meshcore_contacts.MeshcoreContactParser."
            "_is_error_event",
            return_value=False,
        ):
            contacts = MeshcoreContactParser.from_command_result(result)
        self.assertEqual(len(contacts), 1)
        self.assertEqual(contacts[0]["name"], "Alice")
        self.assertEqual(contacts[0]["public_key"], "aabb0011223344")
        self.assertEqual(contacts[0]["last_seen"], 9)

    def test_normalize_payload_dict_and_list(self):
        self.assertEqual(
            len(MeshcoreContactParser.normalize_payload({
                "k": {"adv_name": "A", "public_key": "aa"},
                "n": 1,
            })),
            1,
        )
        self.assertEqual(
            MeshcoreContactParser.normalize_payload(None),
            [],
        )

    def test_position_survives_contact_parsing_without_a_name(self):
        result = SimpleNamespace(payload={"aa": {
            "public_key": "aabb0011223344", "adv_lat": "0", "adv_lon": "12.5",
        }})
        with patch.object(MeshcoreContactParser, "_is_error_event", return_value=False):
            contacts = MeshcoreContactParser.from_command_result(result)
        self.assertEqual(len(contacts), 1)
        self.assertEqual(contacts[0]["name"], "")
        self.assertEqual(contacts[0]["adv_lat"], 0.0)
        self.assertEqual(contacts[0]["adv_lon"], 12.5)

    def test_invalid_or_unset_position_is_dropped_as_a_pair(self):
        for lat, lon in [
            (None, 10), (10, None), (0, 0), (91, 10), (10, -181),
            (float("nan"), 10), (10, float("inf")), (True, 10),
            (10, False), ("bad", 10), ([], 10),
        ]:
            with self.subTest(lat=lat, lon=lon):
                contact = MeshcoreContactParser._entries_to_contacts([{
                    "public_key": "aabb0011223344", "adv_name": "Test",
                    "adv_lat": lat, "adv_lon": lon,
                }])[0]
                self.assertIsNone(contact["adv_lat"])
                self.assertIsNone(contact["adv_lon"])


class TestMeshcoreContactCache(unittest.TestCase):

    def test_fresh_then_stale(self):
        cache = MeshcoreContactCache(ttl_seconds=60.0)
        self.assertIsNone(cache.get_fresh())
        cache.store([{"name": "A", "public_key": "aa"}])
        fresh = cache.get_fresh()
        self.assertEqual(len(fresh), 1)
        cache.invalidate()
        self.assertIsNone(cache.get_fresh())
        self.assertEqual(len(cache.get_stale()), 1)

    def test_soft_fail_starts_cooldown_with_empty_roster(self):
        cache = MeshcoreContactCache(ttl_seconds=60.0)
        self.assertIsNone(cache.get_fresh())
        cache.note_soft_fail()
        # Empty list (not None) so callers skip another live fetch.
        self.assertEqual(cache.get_fresh(), [])


if __name__ == "__main__":
    unittest.main()
