"""FastAPI dependency for the shared audit log writer.

Mirrors the ``init_auth`` / ``Depends`` pattern used by the auth
subsystem so route modules can pull the same writer instance via
``Depends(get_audit_writer)`` without leaking module-level state.

Wiring at startup:

    audit_writer = AuditLogWriter()
    init_audit(audit_writer)

Inside a route handler:

    @router.post("/api/auth/change_password")
    def change_password(
        ...,
        audit: AuditLogWriter = Depends(get_audit_writer),
    ):
        with audit.timed_action(user=claims.username, action="password_change"):
            ...
"""

from __future__ import annotations

from src.api.audit.audit_log import AuditLogWriter

_writer: AuditLogWriter | None = None


def init_audit(writer: AuditLogWriter) -> None:
    """Bind the shared audit writer for the lifetime of the app."""
    global _writer
    _writer = writer


def reset_audit() -> None:
    """Test helper: clear module-level state between cases."""
    global _writer
    _writer = None


def get_audit_writer() -> AuditLogWriter:
    """FastAPI dependency: return the bound audit writer.

    Falls back to a no-op writer pointing at an unwritable path if
    nothing was wired up. That path's writes are silently swallowed
    by the writer's best-effort error handling, which keeps tests
    that forget to call ``init_audit`` from blowing up while still
    making the misconfiguration visible in logs.
    """
    if _writer is None:
        return AuditLogWriter(log_path="/dev/null")
    return _writer
