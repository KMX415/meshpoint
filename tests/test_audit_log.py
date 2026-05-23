"""Coverage for the append-only JSONL audit log writer.

Asserts the contract dashboard auditing relies on:

* Every ``write`` call produces exactly one JSON line on disk.
* ``timed_action`` records elapsed milliseconds and final result on
  both happy and exception paths, with the original exception
  re-raised intact.
* Sensitive keys (password, secret, token, jwt, key) are redacted at
  every depth before serialization, never reaching the file.
* Concurrent writers do not interleave bytes within a single line.
"""

from __future__ import annotations

import json
import threading
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from src.api.audit.audit_log import AuditLogWriter, _redact


class _AuditTestBase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = TemporaryDirectory()
        self.tmp_path = Path(self._tmp.name)
        self.log_path = self.tmp_path / "admin_audit.jsonl"
        self.writer = AuditLogWriter(log_path=self.log_path)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def read_lines(self) -> list[dict]:
        if not self.log_path.exists():
            return []
        with self.log_path.open("r", encoding="utf-8") as fh:
            return [json.loads(line) for line in fh if line.strip()]


class TestWriteShape(_AuditTestBase):
    def test_single_write_produces_one_line(self) -> None:
        self.writer.write(user="kurt", action="restart_service")
        lines = self.read_lines()
        self.assertEqual(len(lines), 1)
        entry = lines[0]
        self.assertEqual(entry["user"], "kurt")
        self.assertEqual(entry["action"], "restart_service")
        self.assertEqual(entry["result"], "success")
        self.assertEqual(entry["params"], {})
        self.assertIn("ts", entry)
        self.assertIn("duration_ms", entry)
        self.assertNotIn("error", entry)

    def test_multiple_writes_appended(self) -> None:
        self.writer.write(user="kurt", action="a")
        self.writer.write(user="kurt", action="b")
        self.writer.write(user="kurt", action="c")
        actions = [entry["action"] for entry in self.read_lines()]
        self.assertEqual(actions, ["a", "b", "c"])

    def test_anonymous_user_default(self) -> None:
        self.writer.write(user="", action="probe")
        entry = self.read_lines()[0]
        self.assertEqual(entry["user"], "anonymous")

    def test_error_field_only_present_when_set(self) -> None:
        self.writer.write(user="x", action="ok")
        self.assertNotIn("error", self.read_lines()[0])
        self.writer.write(user="x", action="bad", result="error", error="boom")
        last = self.read_lines()[-1]
        self.assertEqual(last["result"], "error")
        self.assertEqual(last["error"], "boom")


class TestTimedAction(_AuditTestBase):
    def test_happy_path_records_success_and_duration(self) -> None:
        with self.writer.timed_action(user="kurt", action="quick"):
            time.sleep(0.01)
        entry = self.read_lines()[0]
        self.assertEqual(entry["result"], "success")
        self.assertGreaterEqual(entry["duration_ms"], 5)
        self.assertNotIn("error", entry)

    def test_exception_path_records_error_and_reraises(self) -> None:
        with self.assertRaises(RuntimeError):
            with self.writer.timed_action(user="kurt", action="bang"):
                raise RuntimeError("disk full")
        entry = self.read_lines()[0]
        self.assertEqual(entry["result"], "error")
        self.assertEqual(entry["error"], "disk full")
        self.assertGreaterEqual(entry["duration_ms"], 0)

    def test_in_block_param_mutation_persists_to_log(self) -> None:
        with self.writer.timed_action(
            user="kurt", action="wipe", params={"target": "phantoms"}
        ) as ctx:
            ctx.params["count"] = 7
        entry = self.read_lines()[0]
        self.assertEqual(entry["params"], {"target": "phantoms", "count": 7})


class TestRedaction(_AuditTestBase):
    def test_top_level_password_redacted(self) -> None:
        self.writer.write(
            user="kurt",
            action="password_change",
            params={"current_password": "hunter2", "new_password": "shrubbery"},
        )
        entry = self.read_lines()[0]
        self.assertEqual(entry["params"]["current_password"], "<redacted>")
        self.assertEqual(entry["params"]["new_password"], "<redacted>")

    def test_nested_secret_redacted(self) -> None:
        self.writer.write(
            user="kurt",
            action="config_update",
            params={"web_auth": {"jwt_secret": "abc123", "expiry_minutes": 60}},
        )
        entry = self.read_lines()[0]
        self.assertEqual(entry["params"]["web_auth"]["jwt_secret"], "<redacted>")
        self.assertEqual(entry["params"]["web_auth"]["expiry_minutes"], 60)

    def test_psk_key_redacted(self) -> None:
        self.writer.write(
            user="kurt",
            action="channel_add",
            params={"name": "private-1", "key": "AAAA=="},
        )
        entry = self.read_lines()[0]
        self.assertEqual(entry["params"]["key"], "<redacted>")
        self.assertEqual(entry["params"]["name"], "private-1")

    def test_token_substring_redacted(self) -> None:
        result = _redact({"refresh_token": "xyz", "tokens_used": 5})
        self.assertEqual(result["refresh_token"], "<redacted>")
        self.assertEqual(result["tokens_used"], "<redacted>")

    def test_list_of_dicts_redacted(self) -> None:
        self.writer.write(
            user="kurt",
            action="bulk",
            params={"channels": [{"name": "a", "key": "K1"}, {"name": "b", "key": "K2"}]},
        )
        entry = self.read_lines()[0]
        self.assertEqual(entry["params"]["channels"][0]["key"], "<redacted>")
        self.assertEqual(entry["params"]["channels"][1]["key"], "<redacted>")
        self.assertEqual(entry["params"]["channels"][0]["name"], "a")

    def test_non_sensitive_key_not_redacted(self) -> None:
        self.writer.write(
            user="kurt",
            action="restart_service",
            params={"reason": "user_initiated", "duration": 5},
        )
        entry = self.read_lines()[0]
        self.assertEqual(entry["params"]["reason"], "user_initiated")
        self.assertEqual(entry["params"]["duration"], 5)


class TestConcurrency(_AuditTestBase):
    def test_concurrent_writes_serialize_cleanly(self) -> None:
        thread_count = 8
        per_thread = 25

        def worker(idx: int) -> None:
            for j in range(per_thread):
                self.writer.write(
                    user=f"u{idx}",
                    action=f"a{idx}_{j}",
                )

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(thread_count)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        lines = self.read_lines()
        self.assertEqual(len(lines), thread_count * per_thread)
        for entry in lines:
            self.assertIn("user", entry)
            self.assertIn("action", entry)


class TestPathPreparation(_AuditTestBase):
    def test_creates_parent_directory_lazily(self) -> None:
        nested = self.tmp_path / "deep" / "nested" / "audit.jsonl"
        writer = AuditLogWriter(log_path=nested)
        self.assertFalse(nested.parent.exists())
        writer.write(user="kurt", action="probe")
        self.assertTrue(nested.exists())

    def test_disk_failure_does_not_raise(self) -> None:
        bad = AuditLogWriter(log_path=Path("/this/does/not/exist/and/cannot/be/made/audit.jsonl"))
        bad.write(user="kurt", action="probe")


if __name__ == "__main__":
    unittest.main()
