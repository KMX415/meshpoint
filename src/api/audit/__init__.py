"""Append-only audit log for admin-mutating actions.

Every endpoint that changes state on the device behind admin auth
emits one entry per action. The log is JSONL at
``/opt/meshpoint/data/admin_audit.jsonl`` by default; survives
restarts; readable only by the service user.

Usage:

    audit = AuditLogWriter()
    with audit.timed_action(user="kurt", action="restart_service") as ctx:
        do_the_thing()

The ``timed_action`` context manager records the duration and final
result automatically; raise inside the ``with`` block to record an
error. Direct ``audit.write(...)`` is fine for cases where the
caller wants full control.
"""

from src.api.audit.audit_log import AuditEntry, AuditLogWriter

__all__ = ["AuditEntry", "AuditLogWriter"]
