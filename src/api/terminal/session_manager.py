"""Registry of active PTY sessions for the dashboard terminal.

One ``SessionManager`` instance lives at app scope. The terminal WS
handler asks it for a freshly-spawned session, holds the returned
session id for the lifetime of the connection, and asks the manager
to clean it up on disconnect. Cleanup also runs on app shutdown so
the host doesn't accumulate orphan shells across restarts.

Concurrency model: synchronous lock around the registry dict. PTY
I/O is forwarded directly via the session object, not the manager,
so contention is limited to spawn/destroy. ``max_sessions`` is a
hard cap to keep one runaway client from exhausting PIDs.
"""

from __future__ import annotations

import logging
import secrets
import threading
from dataclasses import dataclass
from typing import Optional

from src.api.terminal.pty_session import PtySession, PtyUnavailable

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SpawnResult:
    """Returned by :meth:`SessionManager.spawn`."""

    session_id: str
    session: PtySession


class SessionManager:
    """Tracks live PTY sessions, keyed by an opaque session id.

    The id is a 128-bit URL-safe random token generated server-side
    so a client cannot forge or guess another session's identifier.
    """

    def __init__(
        self,
        *,
        max_sessions: int = 4,
        shell: str = "/bin/bash",
        cwd: Optional[str] = None,
    ) -> None:
        self._max_sessions = max_sessions
        self._shell = shell
        self._cwd = cwd
        self._sessions: dict[str, PtySession] = {}
        self._lock = threading.Lock()

    @property
    def max_sessions(self) -> int:
        return self._max_sessions

    def session_count(self) -> int:
        with self._lock:
            return len(self._sessions)

    def spawn(self, *, rows: int = 40, cols: int = 120) -> SpawnResult:
        """Create a new PTY-backed session.

        Raises ``RuntimeError`` if the session cap has been reached
        and ``PtyUnavailable`` on non-POSIX hosts.
        """
        with self._lock:
            if len(self._sessions) >= self._max_sessions:
                raise RuntimeError("max terminal sessions reached")
        try:
            session = PtySession.spawn(
                shell=self._shell, cwd=self._cwd, rows=rows, cols=cols
            )
        except PtyUnavailable:
            raise
        session_id = secrets.token_urlsafe(16)
        with self._lock:
            self._sessions[session_id] = session
        logger.info("terminal session spawned id=%s pid=%d", session_id, session.pid)
        return SpawnResult(session_id=session_id, session=session)

    def get(self, session_id: str) -> Optional[PtySession]:
        with self._lock:
            return self._sessions.get(session_id)

    def destroy(self, session_id: str) -> bool:
        """Terminate the session and remove it from the registry."""
        with self._lock:
            session = self._sessions.pop(session_id, None)
        if session is None:
            return False
        session.terminate()
        logger.info("terminal session destroyed id=%s", session_id)
        return True

    def shutdown(self) -> None:
        """Tear down every active session (called from app lifespan)."""
        with self._lock:
            sessions = list(self._sessions.items())
            self._sessions.clear()
        for session_id, session in sessions:
            try:
                session.terminate()
            except Exception:
                logger.debug(
                    "terminate raised during shutdown id=%s",
                    session_id,
                    exc_info=True,
                )
