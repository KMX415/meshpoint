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

    def terminate(self, *, grace_seconds: float = 0.5) -> None:
        """Send SIGTERM, then SIGKILL after ``grace_seconds``."""
        if self._closed:
            return
        try:
            os.kill(self._pid, signal.SIGTERM)
        except (ProcessLookupError, OSError):
            pass
        deadline = grace_seconds
        # ``waitpid`` with WNOHANG polled in 50 ms increments avoids
        # importing asyncio here (this class is sync on purpose).
        import time as _time
        while deadline > 0:
            try:
                pid, _status = os.waitpid(self._pid, os.WNOHANG)
                if pid != 0:
                    break
            except ChildProcessError:
                break
            _time.sleep(0.05)
            deadline -= 0.05
        else:
            try:
                os.kill(self._pid, signal.SIGKILL)
            except (ProcessLookupError, OSError):
                pass
            try:
                os.waitpid(self._pid, 0)
            except ChildProcessError:
                pass
        try:
            os.close(self._master_fd)
        except OSError:
            pass
        self._closed = True

    def is_alive(self) -> bool:
        if self._closed:
            return False
        try:
            pid, _status = os.waitpid(self._pid, os.WNOHANG)
            return pid == 0
        except ChildProcessError:
            return False
