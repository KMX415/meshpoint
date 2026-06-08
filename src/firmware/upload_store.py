"""In-memory staging for uploaded firmware binaries."""
from __future__ import annotations

import secrets
import time
from dataclasses import dataclass
from pathlib import Path
from threading import Lock


@dataclass
class UploadRecord:
    upload_id: str
    path: Path
    filename: str
    size_bytes: int
    created_at: float


class FirmwareUploadStore:
    """Short-lived upload registry keyed by opaque upload_id."""

    def __init__(self, *, ttl_seconds: float = 3600.0) -> None:
        self._ttl = ttl_seconds
        self._records: dict[str, UploadRecord] = {}
        self._lock = Lock()

    def store(self, path: Path, filename: str, size_bytes: int) -> str:
        self._prune_expired()
        upload_id = secrets.token_urlsafe(16)
        record = UploadRecord(
            upload_id=upload_id,
            path=path,
            filename=filename,
            size_bytes=size_bytes,
            created_at=time.monotonic(),
        )
        with self._lock:
            self._records[upload_id] = record
        return upload_id

    def get(self, upload_id: str) -> UploadRecord | None:
        self._prune_expired()
        with self._lock:
            return self._records.get(upload_id)

    def pop(self, upload_id: str) -> UploadRecord | None:
        self._prune_expired()
        with self._lock:
            return self._records.pop(upload_id, None)

    def _prune_expired(self) -> None:
        cutoff = time.monotonic() - self._ttl
        with self._lock:
            expired = [
                uid
                for uid, rec in self._records.items()
                if rec.created_at < cutoff
            ]
            for uid in expired:
                self._records.pop(uid, None)
