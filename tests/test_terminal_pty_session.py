"""Focused POSIX cleanup regressions; no server, hardware or network."""
import errno
import os
import signal
import time
import unittest
from unittest import mock

from src.api.terminal.pty_session import PtySession


@unittest.skipUnless(os.name == "posix", "POSIX PTY lifecycle")
class TestPtyCleanup(unittest.TestCase):
    def session(self):
        return PtySession(master_fd=99, pid=12345, shell="/bin/sh")

    def test_eof_and_eio_still_reap_and_close(self):
        for outcome in (b"", OSError(errno.EIO, "PTY EOF")):
            with self.subTest(outcome=type(outcome).__name__):
                s = self.session()
                with mock.patch("select.select", return_value=([99], [], [])), \
                     mock.patch("os.read", side_effect=[outcome]):
                    self.assertEqual(s.read_nonblocking(), b"")
                self.assertTrue(s.closed)
                with mock.patch("os.waitpid", return_value=(12345, 0)) as wait, \
                     mock.patch("os.kill") as kill, mock.patch("os.close") as close:
                    s.terminate()
                    s.terminate()
                    wait.assert_called_once_with(12345, os.WNOHANG)
                    kill.assert_not_called()
                    close.assert_called_once_with(99)

    def test_is_alive_reaped_child_is_never_signalled(self):
        s = self.session()
        with mock.patch("os.waitpid", return_value=(12345, 0)) as wait, \
             mock.patch("os.kill") as kill, mock.patch("os.close") as close:
            self.assertFalse(s.is_alive())
            s.terminate()
            self.assertFalse(s.is_alive())
            wait.assert_called_once()
            kill.assert_not_called()
            close.assert_called_once_with(99)

    def test_externally_reaped_child_is_never_signalled(self):
        s = self.session()
        with mock.patch("os.waitpid", side_effect=ChildProcessError) as wait, \
             mock.patch("os.kill") as kill, mock.patch("os.close") as close:
            s.terminate(grace_seconds=0)
            s.terminate()
            wait.assert_called_once()
            kill.assert_not_called()
            close.assert_called_once_with(99)

    def test_live_child_receives_term_and_is_reaped(self):
        s = self.session()
        with mock.patch("os.waitpid", side_effect=[(0, 0), (12345, 0)]), \
             mock.patch("os.kill") as kill, mock.patch("os.close") as close:
            s.terminate()
            kill.assert_called_once_with(12345, signal.SIGTERM)
            close.assert_called_once_with(99)

    def test_unresponsive_child_is_killed_and_reaped(self):
        s = self.session()
        with mock.patch("os.waitpid", side_effect=[(0, 0), (0, 0), (12345, 0)]) as wait, \
             mock.patch("os.kill") as kill, mock.patch("os.close") as close:
            s.terminate(grace_seconds=0)
            self.assertEqual(kill.call_args_list, [mock.call(12345, signal.SIGTERM),
                                                 mock.call(12345, signal.SIGKILL)])
            self.assertEqual(wait.call_args_list[-1], mock.call(12345, 0))
            close.assert_called_once_with(99)

    def test_failed_signal_still_closes_fd(self):
        s = self.session()
        with mock.patch("os.waitpid", return_value=(0, 0)), \
             mock.patch("os.kill", side_effect=PermissionError), \
             mock.patch("os.close") as close:
            with self.assertRaises(PermissionError):
                s.terminate()
            close.assert_called_once_with(99)

    def test_real_shell_eof_releases_child_and_descriptor(self):
        s = PtySession.spawn(shell="/bin/sh", env={"PATH": "/usr/bin:/bin"})
        try:
            s.write(b"exit\n")
            deadline = time.monotonic() + 5
            while not s.closed and time.monotonic() < deadline:
                s.read_nonblocking(timeout_seconds=0.05)
            self.assertTrue(s.closed, "shell did not reach EOF")
            s.terminate()
            with self.assertRaises(ChildProcessError):
                os.waitpid(s.pid, os.WNOHANG)
            with self.assertRaises(OSError) as error:
                os.fstat(s.master_fd)
            self.assertEqual(error.exception.errno, errno.EBADF)
            # A later descriptor must survive repeated cleanup of the old session.
            fd = os.open(os.devnull, os.O_RDONLY)
            try:
                s.terminate()
                os.fstat(fd)
            finally:
                os.close(fd)
        finally:
            s.terminate()

    def test_real_live_shell_termination(self):
        s = PtySession.spawn(shell="/bin/sh", env={"PATH": "/usr/bin:/bin"})
        try:
            self.assertTrue(s.is_alive())
            s.terminate(grace_seconds=0.1)
            self.assertFalse(s.is_alive())
            with self.assertRaises(ChildProcessError):
                os.waitpid(s.pid, os.WNOHANG)
        finally:
            s.terminate()


if __name__ == "__main__":
    unittest.main()
