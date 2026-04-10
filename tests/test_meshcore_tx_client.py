"""Tests for MeshCoreTxClient static helpers."""

from __future__ import annotations

import unittest

from src.transmit.meshcore_tx_client import MeshCoreTxClient


class TestNormalizeContactPayload(unittest.TestCase):

    def test_dict_keyed_by_pubkey(self):
        payload = {
            "aabb001122": {"adv_name": "Alice", "public_key": "aabb001122"},
            "ccdd334455": {"adv_name": "Bob", "public_key": "ccdd334455"},
        }
        result = MeshCoreTxClient._normalize_contact_payload(payload)
        self.assertEqual(len(result), 2)
        names = {e.get("adv_name") for e in result}
        self.assertIn("Alice", names)
        self.assertIn("Bob", names)

    def test_list_format(self):
        payload = [
            {"adv_name": "Carol", "public_key": "eeff"},
            {"adv_name": "Dave", "public_key": "1122"},
        ]
        result = MeshCoreTxClient._normalize_contact_payload(payload)
        self.assertEqual(len(result), 2)

    def test_list_filters_non_dict(self):
        payload = [
            {"adv_name": "Eve", "public_key": "3344"},
            "not-a-dict",
            42,
        ]
        result = MeshCoreTxClient._normalize_contact_payload(payload)
        self.assertEqual(len(result), 1)

    def test_none_returns_empty(self):
        self.assertEqual(MeshCoreTxClient._normalize_contact_payload(None), [])

    def test_string_returns_empty(self):
        self.assertEqual(MeshCoreTxClient._normalize_contact_payload("nope"), [])

    def test_empty_dict(self):
        self.assertEqual(MeshCoreTxClient._normalize_contact_payload({}), [])

    def test_empty_list(self):
        self.assertEqual(MeshCoreTxClient._normalize_contact_payload([]), [])


if __name__ == "__main__":
    unittest.main()
