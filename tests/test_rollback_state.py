"""Tests for persisted rollback SHA across dashboard reload."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from src.api.update.rollback_state import (
    clear_rollback_state,
    read_rollback_state,
    resolve_rollback_state_path,
    write_rollback_state,
)


class TestRollbackState(unittest.TestCase):
    def test_resolve_path_next_to_database(self) -> None:
        path = resolve_rollback_state_path("data/concentrator.db")
        self.assertEqual(path, Path("/opt/meshpoint/data/update_rollback.json"))

    def test_write_read_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "update_rollback.json"
            self.assertTrue(
                write_rollback_state(
                    "abc123deadbeef",
                    target_branch="feat/v0.7.4",
                    path=path,
                ),
            )
            data = read_rollback_state(path=path)
            self.assertIsNotNone(data)
            assert data is not None
            self.assertEqual(data["pre_update_sha"], "abc123deadbeef")
            self.assertEqual(data["target_branch"], "feat/v0.7.4")

    def test_clear_removes_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "update_rollback.json"
            write_rollback_state("sha1", path=path)
            clear_rollback_state(path=path)
            self.assertIsNone(read_rollback_state(path=path))

    def test_read_missing_returns_none(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "missing.json"
            self.assertIsNone(read_rollback_state(path=path))

    def test_read_rejects_empty_sha(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.json"
            path.write_text(
                json.dumps({"pre_update_sha": ""}),
                encoding="utf-8",
            )
            self.assertIsNone(read_rollback_state(path=path))


if __name__ == "__main__":
    unittest.main()
