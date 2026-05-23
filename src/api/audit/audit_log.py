"""Append-only JSONL audit log writer.

Single responsibility: turn a structured action record into one
line of JSON appended to ``/opt/meshpoint/data/admin_audit.jsonl``,
without leaking secrets and without losing entries during concurrent
admin actions. No HTTP, no auth, no business logic.

The writer is synchronous because:

* JSONL append is a single ``write`` syscall on a small line; cheap
  enough to call inline from FastAPI handlers.
* Concurrent writes are serialized with an in-process ``Lock`` so
  the order on disk matches caller intent.
* If the disk write fails (full disk, permission flip), we log the
  failure to stderr and proceed -- the audit log is best-effort
  observability, not authoritative state.

Sanitization is keyword-based. Any nested key matching one of
``_SENSITIVE_KEYS`` (password, key, secret, etc.) gets replaced with
``"<redacted>"`` before serialization. Callers should still avoid
passing raw secrets in ``params`` -- the redactor is a backstop, not
a license to be sloppy.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import threading
import time
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

logger = logging.getLogger(__name__)

DEFAULT_LOG_PATH = Path("/opt/meshpoint/data/admin_audit.jsonl")
DEFAULT_FILE_MODE = 0o640
DEFAULT_DIR_MODE = 0o750

_SENSITIVE_KEYS = frozenset(
    {
        "password",
        "current_password",
        "new_password",
        "confirm_password",
        "viewer_password",
        "admin_password",
        "secret",
        "jwt_secret",
        "session_secret",
        "key",
        "psk",
        "channel_key",
        "raw_key",
        "token",
        "auth",
        "authorization",
        "cookie",
    }
)
_REDACTED = "<redacted>"


@dataclass
class AuditEntry:
    """One line of the audit log.

    Built by ``AuditLogWriter.timed_action`` automatically; callers
    rarely instantiate directly. Field order matters for JSON
    consistency across restarts.
    """

    ts: str
    user: str
    action: str
    params: dict[str, Any] = field(default_factory=dict)
    result: str = "success"
    duration_ms: int = 0
    error: str | None = None

    def to_json(self) -> str:
        payload = asdict(self)
        if self.error is None:
            payload.pop("error", None)
        return json.dumps(payload, sort_keys=False, separators=(",", ":"))


class AuditLogWriter:
    """Synchronous, lock-protected JSONL appender.

    Constructed once at startup and shared across handlers via
    dependency injection. Tests pass a ``log_path`` inside ``tmp_path``
    so the production path is never touched.
    """

    def __init__(
        self,
        log_path: Path | str = DEFAULT_LOG_PATH,
        file_mode: int = DEFAULT_FILE_MODE,
        dir_mode: int = DEFAULT_DIR_MODE,
    ) -> None:
        self._path = Path(log_path)
        self._file_mode = file_mode
        self._dir_mode = dir_mode
        self._lock = threading.Lock()
        self._initialized = False

    @property
    def path(self) -> Path:
        return self._path

    def write(
        self,
        *,
        user: str,
        action: str,
        params: dict[str, Any] | None = None,
        result: str = "success",
        duration_ms: int = 0,
        error: str | None = None,
    ) -> None:
        """Append one entry. Best-effort; never raises to caller."""
        entry = AuditEntry(
            ts=_now_iso(),
            user=user or "anonymous",
            action=action,
            params=_redact(params or {}),
            result=result,
            duration_ms=int(duration_ms),
            error=error,
        )
        self._write_entry(entry)

    @contextmanager
    def timed_action(
        self,
        *,
        user: str,
        action: str,
        params: dict[str, Any] | None = None,
    ) -> Iterator["_TimedActionContext"]:
        """Wrap a code block; emit an audit entry on exit.

        On normal exit, ``result="success"`` and the elapsed wall-clock
        is recorded. On an exception, ``result="error"`` and the error
        message is captured (the exception still propagates to the
        caller). Mutate ``ctx.params`` inside the block to add fields
        observed during execution (e.g. discovered counts).
        """
        ctx = _TimedActionContext(params=dict(params or {}))
        started = time.perf_counter()
        try:
            yield ctx
        except Exception as exc:
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            self.write(
                user=user,
                action=action,
                params=ctx.params,
                result=ctx.result if ctx.result_is_set() else "error",
                duration_ms=elapsed_ms,
                error=str(exc) or exc.__class__.__name__,
            )
            raise
        else:
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            self.write(
                user=user,
                action=action,
                params=ctx.params,
                result=ctx.result if ctx.result_is_set() else "success",
                duration_ms=elapsed_ms,
                error=ctx.error,
            )

    def _write_entry(self, entry: AuditEntry) -> None:
        line = entry.to_json() + "\n"
        with self._lock:
            try:
                self._ensure_path_ready()
                with open(self._path, "a", encoding="utf-8") as fh:
                    fh.write(line)
            except OSError as exc:
                print(
                    f"audit_log: write failed ({exc.__class__.__name__}: {exc})",
                    file=sys.stderr,
                )

    def _ensure_path_ready(self) -> None:
        if self._initialized and self._path.exists():
            return
        parent = self._path.parent
        try:
            parent.mkdir(parents=True, exist_ok=True)
            try:
                os.chmod(parent, self._dir_mode)
            except OSError:
                pass
            if not self._path.exists():
                self._path.touch()
            try:
                os.chmod(self._path, self._file_mode)
            except OSError:
                pass
            self._initialized = True
        except OSError as exc:
            print(
                f"audit_log: failed to prepare {self._path} ({exc})",
                file=sys.stderr,
            )


@dataclass
class _TimedActionContext:
    """Mutable handle yielded by ``timed_action`` for in-block updates."""

    params: dict[str, Any]
    error: str | None = None
    _result: str | None = None

    @property
    def result(self) -> str:
        return self._result or "success"

    def set_result(self, value: str) -> None:
        self._result = value

    def result_is_set(self) -> bool:
        return self._result is not None


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.") + (
        f"{int(time.time() * 1000) % 1000:03d}Z"
    )


def _redact(value: Any) -> Any:
    """Recursively replace sensitive-keyed values with ``"<redacted>"``."""
    if isinstance(value, dict):
        return {
            k: (_REDACTED if _is_sensitive_key(k) else _redact(v))
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [_redact(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_redact(item) for item in value)
    return value


def _is_sensitive_key(key: Any) -> bool:
    if not isinstance(key, str):
        return False
    lowered = key.lower()
    if lowered in _SENSITIVE_KEYS:
        return True
    return any(token in lowered for token in ("password", "secret", "token"))
