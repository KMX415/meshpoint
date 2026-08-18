"""Short-lived firmware upload store for custom DFU zip / UF2 drops."""

from __future__ import annotations

import secrets
import time
from pathlib import Path
from typing import Optional

_ALLOWED_SUFFIXES = {".zip", ".uf2"}
_MAX_BYTES = 32 * 1024 * 1024
_TTL_SECONDS = 3600


class FirmwareUploadStore:
    """Persist uploaded ``.zip`` / ``.uf2`` blobs under a cache root."""

    def __init__(self, root: Path) -> None:
        self._root = root
        self._root.mkdir(parents=True, exist_ok=True)

    def save(self, filename: str, data: bytes) -> str:
        suffix = Path(filename).suffix.lower()
        if suffix not in _ALLOWED_SUFFIXES:
            raise ValueError("Only .zip and .uf2 uploads are allowed")
        if len(data) == 0:
            raise ValueError("Empty upload")
        if len(data) > _MAX_BYTES:
            raise ValueError(f"Upload exceeds {_MAX_BYTES} byte limit")
        self._purge_expired()
        upload_id = secrets.token_hex(16)
        dest = self._root / f"{upload_id}{suffix}"
        dest.write_bytes(data)
        dest.chmod(0o644)
        return upload_id

    def resolve(self, upload_id: str) -> Optional[Path]:
        if not upload_id or any(c in upload_id for c in "/\\.."):
            return None
        matches = list(self._root.glob(f"{upload_id}.*"))
        if not matches:
            return None
        path = matches[0]
        if path.suffix.lower() not in _ALLOWED_SUFFIXES:
            return None
        age = time.time() - path.stat().st_mtime
        if age > _TTL_SECONDS:
            path.unlink(missing_ok=True)
            return None
        return path

    def _purge_expired(self) -> None:
        now = time.time()
        for path in self._root.iterdir():
            if not path.is_file():
                continue
            if now - path.stat().st_mtime > _TTL_SECONDS:
                path.unlink(missing_ok=True)
