"""POSIX PTY wrapper for the dashboard terminal.

Wraps a single child process attached to a pseudo-terminal. Reads
return raw bytes (the frontend's xterm.js handles the VT100 escape
sequences); writes accept whatever the user typed plus xterm-style
control inputs. Resizing the window is a separate ioctl call.

The class is **POSIX-only** by design. Importing on Windows raises
``PtyUnavailable`` so the module can still be unit-tested without
actually starting a process there. CI runs on Linux so production
parity is preserved; Windows tests cover the catalog + manager.

Lifecycle:

    session = PtySession.spawn(shell="/bin/bash")
    session.write(b"ls\\n")
    chunk = session.read_nonblocking(timeout_seconds=0.1)
    session.resize(rows=40, cols=120)
    session.terminate()

Threading model: the session is intentionally simple -- the caller
(``SessionManager`` / WS handler) is responsible for spawning a
reader task that loops on :meth:`read_nonblocking` and forwards
chunks to the WebSocket. Inside this class we only own the file
descriptor and the child PID.
"""

from __future__ import annotations

import errno
import logging
import os
import select
import signal
from typing import Optional

logger = logging.getLogger(__name__)

_HAS_PTY = os.name == "posix"


class PtyUnavailable(RuntimeError):
    """Raised when PTY operations are requested on a non-POSIX host."""


class PtySession:
    """A single child process attached to a pseudo-terminal.

    Construction goes through :meth:`spawn` rather than ``__init__``
    so callers who hold a stub session (tests, fakes) can subclass
    cleanly without forking a process.
    """

    def __init__(self, master_fd: int, pid: int, *, shell: str) -> None:
        self._master_fd = master_fd
        self._pid = pid
        self._shell = shell
        self._closed = False
        self._child_reaped = False
        self._fd_closed = False

    @classmethod
    def spawn(
        cls,
        *,
        shell: str = "/bin/bash",
        cwd: Optional[str] = None,
        env: Optional[dict[str, str]] = None,
        rows: int = 40,
        cols: int = 120,
    ) -> "PtySession":
        if not _HAS_PTY:
            raise PtyUnavailable(
                "PtySession requires a POSIX host (pty/fcntl unavailable)"
            )
        import pty

        pid, master_fd = pty.fork()
        if pid == 0:
            try:
                if cwd:
                    os.chdir(cwd)
                final_env = env or os.environ.copy()
                final_env.setdefault("TERM", "xterm-256color")
                os.execvpe(shell, [shell, "-l"], final_env)
            except Exception:
                os._exit(127)
        session = cls(master_fd=master_fd, pid=pid, shell=shell)
        session.resize(rows=rows, cols=cols)
        return session

    @property
    def master_fd(self) -> int:
        return self._master_fd

    @property
    def pid(self) -> int:
        return self._pid

    @property
    def shell(self) -> str:
        return self._shell

    @property
    def closed(self) -> bool:
        return self._closed

    def write(self, data: bytes) -> int:
        if self._closed:
            return 0
        try:
            return os.write(self._master_fd, data)
        except OSError as exc:
            if exc.errno in (errno.EIO, errno.EBADF):
                self._closed = True
                return 0
            raise

    def read_nonblocking(
        self, *, timeout_seconds: float = 0.1, max_bytes: int = 65536
    ) -> bytes:
        if self._closed:
            return b""
        try:
            ready, _, _ = select.select(
                [self._master_fd], [], [], timeout_seconds
            )
        except (OSError, ValueError):
            self._closed = True
            return b""
        if not ready:
            return b""
        try:
            chunk = os.read(self._master_fd, max_bytes)
        except OSError as exc:
            if exc.errno in (errno.EIO, errno.EBADF):
                self._closed = True
                return b""
            raise
        if not chunk:
            self._closed = True
        return chunk

    def resize(self, *, rows: int, cols: int) -> None:
        """Forward a TIOCSWINSZ ioctl to the slave side of the PTY."""
        if self._closed or not _HAS_PTY:
            return
        import fcntl
        import struct
        import termios

        try:
            packed = struct.pack("HHHH", rows, cols, 0, 0)
            fcntl.ioctl(self._master_fd, termios.TIOCSWINSZ, packed)
        except OSError:
            logger.debug("PTY resize ioctl failed", exc_info=True)

    def _poll_child(self) -> bool:
        """Reap an exited child once; never signal a PID after losing ownership."""
        if not self._child_reaped:
            try:
                pid, _status = os.waitpid(self._pid, os.WNOHANG)
                self._child_reaped = pid != 0
            except ChildProcessError:
                self._child_reaped = True
        return self._child_reaped

    def terminate(self, *, grace_seconds: float = 0.5) -> None:
        """Reap the child and close the PTY, including after read-side EOF."""
        import time as _time

        self._closed = True
        try:
            if not self._poll_child():
                try:
                    os.kill(self._pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
                deadline = _time.monotonic() + max(0.0, grace_seconds)
                while not self._poll_child():
                    remaining = deadline - _time.monotonic()
                    if remaining <= 0:
                        try:
                            os.kill(self._pid, signal.SIGKILL)
                        except ProcessLookupError:
                            pass
                        try:
                            os.waitpid(self._pid, 0)
                        except ChildProcessError:
                            pass
                        self._child_reaped = True
                        break
                    _time.sleep(min(0.05, remaining))
        finally:
            if not self._fd_closed:
                # Mark before close: retrying a close can affect a reused descriptor.
                self._fd_closed = True
                try:
                    os.close(self._master_fd)
                except OSError:
                    pass

    def is_alive(self) -> bool:
        return not self._poll_child() and not self._closed
