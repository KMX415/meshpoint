"""Tests for the PTY session registry.

Two layers of coverage:

1. POSIX-only integration: spawn a real shell, write/read, terminate.
   Skipped on Windows (no ``pty`` / ``fcntl``).

2. Cross-platform structural: cap enforcement and id-uniqueness via a
   subclass that overrides ``spawn`` so the cap path is exercised on
   Windows CI / local boxes.
"""

from __future__ import annotations

import os
import time
import unittest
from typing import Optional
from unittest import mock

from src.api.terminal.pty_session import PtySession, PtyUnavailable
from src.api.terminal.session_manager import SessionManager

_HAS_PTY = os.name == "posix"


class _FakePtySession(PtySession):
    """Stand-in that skips fork() so cap tests run on Windows."""

    def __init__(self, master_fd: int = -1, pid: int = 0) -> None:
        super().__init__(master_fd=master_fd, pid=pid, shell="/bin/false")
        self._closed = False

    def write(self, data: bytes) -> int:
        return len(data)

    def read_nonblocking(self, *, timeout_seconds: float = 0.1, max_bytes: int = 65536) -> bytes:
        return b""

    def resize(self, *, rows: int, cols: int) -> None:
        return None

    def terminate(self, *, grace_seconds: float = 0.5) -> None:
        self._closed = True

    def is_alive(self) -> bool:
        return not self._closed


class TestSessionManagerCap(unittest.TestCase):
    def test_max_sessions_cap_enforced(self) -> None:
        manager = SessionManager(max_sessions=2)
        with mock.patch.object(
            PtySession, "spawn",
            side_effect=lambda **_kwargs: _FakePtySession(),
        ):
            first = manager.spawn()
            second = manager.spawn()
            self.assertEqual(manager.session_count(), 2)
            with self.assertRaises(RuntimeError):
                manager.spawn()
            manager.destroy(first.session_id)
            self.assertEqual(manager.session_count(), 1)
            manager.destroy(second.session_id)

    def test_destroy_unknown_id_returns_false(self) -> None:
        manager = SessionManager()
        self.assertFalse(manager.destroy("nonexistent"))

    def test_get_returns_session_after_spawn(self) -> None:
        manager = SessionManager()
        with mock.patch.object(
            PtySession, "spawn",
            side_effect=lambda **_kwargs: _FakePtySession(),
        ):
            spawn = manager.spawn()
            self.assertIs(manager.get(spawn.session_id), spawn.session)
            manager.destroy(spawn.session_id)
            self.assertIsNone(manager.get(spawn.session_id))

    def test_shutdown_terminates_every_session(self) -> None:
        manager = SessionManager(max_sessions=3)
        with mock.patch.object(
            PtySession, "spawn",
            side_effect=lambda **_kwargs: _FakePtySession(),
        ):
            manager.spawn()
            manager.spawn()
            self.assertEqual(manager.session_count(), 2)
            manager.shutdown()
            self.assertEqual(manager.session_count(), 0)

    def test_session_ids_are_unique_and_unguessable(self) -> None:
        manager = SessionManager(max_sessions=10)
        ids: set[str] = set()
        with mock.patch.object(
            PtySession, "spawn",
            side_effect=lambda **_kwargs: _FakePtySession(),
        ):
            for _ in range(5):
                spawn = manager.spawn()
                ids.add(spawn.session_id)
                self.assertGreaterEqual(len(spawn.session_id), 16)
        self.assertEqual(len(ids), 5)


@unittest.skipUnless(_HAS_PTY, "PTY tests require POSIX")
class TestPtySessionLive(unittest.TestCase):
    def test_round_trip_with_cat(self) -> None:
        session = PtySession.spawn(shell="/bin/cat")
        try:
            session.write(b"hello terminal\n")
            output = self._drain(session, timeout=2.0)
            self.assertIn(b"hello terminal", output)
        finally:
            session.terminate()
            self.assertTrue(session.closed)

    def test_terminate_kills_running_shell(self) -> None:
        session = PtySession.spawn(shell="/bin/sh")
        try:
            session.write(b"sleep 30\n")
            time.sleep(0.1)
            self.assertTrue(session.is_alive())
        finally:
            session.terminate()
        self.assertFalse(session.is_alive())

    def test_pty_unavailable_raised_on_non_posix(self) -> None:
        with mock.patch("src.api.terminal.pty_session._HAS_PTY", False):
            with self.assertRaises(PtyUnavailable):
                PtySession.spawn(shell="/bin/sh")

    def _drain(self, session: PtySession, *, timeout: float) -> bytes:
        deadline = time.time() + timeout
        chunks: list[bytes] = []
        while time.time() < deadline:
            chunk = session.read_nonblocking(timeout_seconds=0.1)
            if chunk:
                chunks.append(chunk)
                if b"hello terminal" in b"".join(chunks):
                    break
        return b"".join(chunks)


class TestPtyUnavailableOnNonPosix(unittest.TestCase):
    def test_pty_unavailable_is_runtime_error_subclass(self) -> None:
        self.assertTrue(issubclass(PtyUnavailable, RuntimeError))


if __name__ == "__main__":
    unittest.main()
