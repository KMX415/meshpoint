"""Coverage for the audit-writer FastAPI dependency wiring.

Mirrors ``tests/test_auth_dependencies.py``: verifies that
``init_audit`` binds a writer that ``get_audit_writer`` then returns,
and that ``reset_audit`` clears it cleanly so test isolation holds.
"""

from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from src.api.audit import AuditLogWriter
from src.api.audit.dependencies import (
    get_audit_writer,
    init_audit,
    reset_audit,
)


class TestAuditDependencies(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = TemporaryDirectory()
        self.tmp_path = Path(self._tmp.name)
        reset_audit()

    def tearDown(self) -> None:
        reset_audit()
        self._tmp.cleanup()

    def test_get_returns_initialized_writer(self) -> None:
        writer = AuditLogWriter(log_path=self.tmp_path / "a.jsonl")
        init_audit(writer)
        self.assertIs(get_audit_writer(), writer)

    def test_get_without_init_returns_noop_writer(self) -> None:
        writer = get_audit_writer()
        self.assertIsInstance(writer, AuditLogWriter)
        writer.write(user="probe", action="probe")

    def test_reset_clears_state_between_tests(self) -> None:
        a = AuditLogWriter(log_path=self.tmp_path / "a.jsonl")
        init_audit(a)
        self.assertIs(get_audit_writer(), a)
        reset_audit()
        not_a = get_audit_writer()
        self.assertIsNot(not_a, a)

    def test_rebind_replaces_writer(self) -> None:
        a = AuditLogWriter(log_path=self.tmp_path / "a.jsonl")
        b = AuditLogWriter(log_path=self.tmp_path / "b.jsonl")
        init_audit(a)
        init_audit(b)
        self.assertIs(get_audit_writer(), b)


if __name__ == "__main__":
    unittest.main()
