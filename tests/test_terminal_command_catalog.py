"""Tests for the web-terminal command catalog.

The catalog is intentionally simple data so the tests pin only the
contract the frontend relies on: a stable id-set, JSON-friendly
serialization, and a category list that preserves first-seen order.
"""

from __future__ import annotations

import unittest

from src.api.terminal.command_catalog import (
    CommandCatalog,
    CommandEntry,
    DEFAULT_CATALOG,
)


class TestDefaultCatalog(unittest.TestCase):
    def test_default_catalog_has_unique_ids(self) -> None:
        ids = [entry.id for entry in DEFAULT_CATALOG]
        self.assertEqual(len(ids), len(set(ids)))

    def test_default_catalog_marks_dangerous_subset(self) -> None:
        dangerous = [e for e in DEFAULT_CATALOG if e.dangerous]
        self.assertTrue(any(e.id == "service-restart" for e in dangerous))

    def test_default_catalog_describes_every_entry(self) -> None:
        for entry in DEFAULT_CATALOG:
            self.assertTrue(entry.label)
            self.assertTrue(entry.command)
            self.assertTrue(entry.description)
            self.assertTrue(entry.category)

    def test_log_buttons_never_use_sudo(self) -> None:
        # journalctl + the `meshpoint logs` CLI both read the system
        # journal as the meshpoint service user without elevation.
        # Prefixing them with sudo hangs the terminal on a password
        # prompt because /etc/sudoers.d/meshpoint intentionally does
        # not whitelist journalctl.
        for entry in DEFAULT_CATALOG:
            if entry.category != "Logs":
                continue
            self.assertFalse(
                entry.command.startswith("sudo "),
                f"Log catalog entry '{entry.id}' must not use sudo: "
                f"{entry.command!r}",
            )


class TestCommandCatalogWrapper(unittest.TestCase):
    def test_payload_is_json_serializable(self) -> None:
        import json
        payload = CommandCatalog().to_payload()
        json.dumps(payload)
        self.assertIsInstance(payload, list)
        self.assertGreater(len(payload), 0)

    def test_categories_preserve_first_seen_order(self) -> None:
        entries = (
            CommandEntry("a", "A", "echo a", "Z", "first"),
            CommandEntry("b", "B", "echo b", "M", "second"),
            CommandEntry("c", "C", "echo c", "Z", "third"),
        )
        self.assertEqual(CommandCatalog(entries).categories(), ["Z", "M"])

    def test_find_returns_matching_entry(self) -> None:
        catalog = CommandCatalog()
        match = catalog.find("service-status")
        self.assertIsNotNone(match)
        self.assertEqual(match.label, "Service status")

    def test_find_returns_none_for_unknown(self) -> None:
        self.assertIsNone(CommandCatalog().find("does-not-exist"))


if __name__ == "__main__":
    unittest.main()
