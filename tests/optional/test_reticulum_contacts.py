"""ContactStore -- the operator petname address book (contacts.py).

Pure disk I/O + validation, no FastAPI / DB, so it runs on the dev Mac.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from apps.reticulum.backend.contacts import ContactStore


class TestContactStore(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.path = Path(self._tmp.name) / "reticulum" / "contacts.json"

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_empty_when_no_file(self) -> None:
        store = ContactStore(self.path)
        self.assertEqual(store.all(), {})
        self.assertIsNone(store.get("abc"))

    def test_set_creates_file_and_entry(self) -> None:
        store = ContactStore(self.path)
        entry = store.set("hash1", "Philster", "voice peer", trusted=True)
        self.assertEqual(entry["petname"], "Philster")
        self.assertEqual(entry["note"], "voice peer")
        self.assertTrue(entry["trusted"])
        self.assertTrue(entry["updated"])  # ISO timestamp filled in
        self.assertTrue(self.path.exists())

    def test_persists_across_instances(self) -> None:
        ContactStore(self.path).set("hash1", "Bob")
        reopened = ContactStore(self.path)
        self.assertEqual(reopened.get("hash1")["petname"], "Bob")

    def test_set_trims_and_rejects_blank_petname(self) -> None:
        store = ContactStore(self.path)
        with self.assertRaises(ValueError):
            store.set("hash1", "   ")
        entry = store.set("hash1", "  Bob  ")
        self.assertEqual(entry["petname"], "Bob")

    def test_set_rejects_overlong_fields(self) -> None:
        store = ContactStore(self.path)
        with self.assertRaises(ValueError):
            store.set("hash1", "x" * 65)
        with self.assertRaises(ValueError):
            store.set("hash1", "ok", "n" * 281)

    def test_set_replaces_existing(self) -> None:
        store = ContactStore(self.path)
        store.set("hash1", "Bob")
        store.set("hash1", "Bobby", "now with a note")
        self.assertEqual(store.get("hash1")["petname"], "Bobby")
        self.assertEqual(store.get("hash1")["note"], "now with a note")
        self.assertEqual(len(store.all()), 1)

    def test_delete(self) -> None:
        store = ContactStore(self.path)
        store.set("hash1", "Bob")
        self.assertTrue(store.delete("hash1"))
        self.assertFalse(store.delete("hash1"))
        self.assertEqual(store.all(), {})

    def test_all_returns_copies(self) -> None:
        store = ContactStore(self.path)
        store.set("hash1", "Bob")
        snapshot = store.all()
        snapshot["hash1"]["petname"] = "mutated"
        self.assertEqual(store.get("hash1")["petname"], "Bob")

    def test_corrupt_file_starts_empty(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text("{ not valid json", "utf-8")
        store = ContactStore(self.path)
        self.assertEqual(store.all(), {})
        # ...and a subsequent write still works
        store.set("hash1", "Bob")
        self.assertEqual(store.get("hash1")["petname"], "Bob")

    def test_display_forms_normalise_to_the_same_key(self) -> None:
        h = "ab" * 16
        store = ContactStore(self.path)
        store.set(f"<{h}>", "Bob")
        # stored under the bare hex; reachable via any display form
        self.assertIn(h, store.all())
        self.assertEqual(store.get(h)["petname"], "Bob")
        self.assertEqual(store.get(f"<{h}>")["petname"], "Bob")
        self.assertTrue(store.delete("ab:ab:ab:ab:ab:ab:ab:ab:ab:ab:ab:ab:ab:ab:ab:ab"))
        self.assertEqual(store.all(), {})

    def test_looks_like_hash(self) -> None:
        from apps.reticulum.backend.contacts import looks_like_hash
        self.assertTrue(looks_like_hash("ab" * 16))
        self.assertTrue(looks_like_hash(f"<{'cd' * 16}>"))
        self.assertFalse(looks_like_hash("nope"))
        self.assertFalse(looks_like_hash("abc"))        # odd length
        self.assertFalse(looks_like_hash("ab"))         # too short
        self.assertFalse(looks_like_hash(""))

    def test_load_skips_malformed_entries(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps({
            "good": {"petname": "Bob", "trusted": True},
            "no_name": {"note": "orphan"},
            "not_a_dict": "nope",
        }), "utf-8")
        store = ContactStore(self.path)
        self.assertEqual(list(store.all()), ["good"])
        self.assertTrue(store.get("good")["trusted"])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
