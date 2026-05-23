"""Web terminal subsystem.

Exposes a PTY-backed shell over a WebSocket plus a curated command
catalog so technical operators can run common diagnostic commands
without leaving the dashboard. Always on for admin sessions; viewers
never see the section.

Public surface:

* ``CommandCatalog``    -- declarative list of one-click commands.
* ``PtySession``        -- a single child PTY process.
* ``SessionManager``    -- registry of active PTY sessions with
                           lifecycle tracking.
* ``terminal_routes``   -- FastAPI router: ``GET /api/terminal/commands``
                           plus ``WS /api/terminal/ws``.
"""

from src.api.terminal.command_catalog import (
    CommandCatalog,
    CommandEntry,
    DEFAULT_CATALOG,
)
from src.api.terminal.pty_session import PtySession, PtyUnavailable
from src.api.terminal.session_manager import SessionManager

__all__ = [
    "CommandCatalog",
    "CommandEntry",
    "DEFAULT_CATALOG",
    "PtySession",
    "PtyUnavailable",
    "SessionManager",
]
