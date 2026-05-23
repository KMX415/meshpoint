"""Persist the pre-update SHA so rollback survives a dashboard reload.

After a successful apply the service restarts and the browser reloads,
wiping in-memory ``ApplyResult``. The operator still needs one-click
rollback to the commit captured before ``git fetch``.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

DEFAULT_ROLLBACK_STATE_PATH = Path("/opt/meshpoint/data/update_rollback.json")
DEFAULT_REPO_ROOT = "/opt/meshpoint"


def resolve_rollback_state_path(
    database_path: str,
    *,
    repo_root: str = DEFAULT_REPO_ROOT,
) -> Path:
    """Same directory as the SQLite DB (``data/update_rollback.json`` by default)."""
    db = Path(database_path)
    if not db.is_absolute():
        db = Path(repo_root) / db
    return db.parent / "update_rollback.json"


def read_rollback_state(
    path: Path = DEFAULT_ROLLBACK_STATE_PATH,
) -> Optional[dict[str, Any]]:
    """Return persisted rollback metadata, or ``None`` if unavailable."""
    try:
        raw = path.read_text(encoding="utf-8")
        data = json.loads(raw)
    except FileNotFoundError:
        return None
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("rollback_state: could not read %s: %s", path, exc)
        return None
    sha = (data.get("pre_update_sha") or "").strip()
    if not sha:
        return None
    return {
        "pre_update_sha": sha,
        "target_branch": data.get("target_branch"),
        "captured_at": data.get("captured_at"),
    }


def write_rollback_state(
    pre_update_sha: str,
    *,
    target_branch: str = "",
    path: Path = DEFAULT_ROLLBACK_STATE_PATH,
) -> bool:
    """Store the SHA to restore on the next dashboard rollback."""
    sha = (pre_update_sha or "").strip()
    if not sha:
        return False
    payload = {
        "pre_update_sha": sha,
        "target_branch": target_branch or None,
        "captured_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(payload, separators=(",", ":")),
            encoding="utf-8",
        )
        logger.info(
            "rollback_state: saved pre-update SHA %s for branch %s at %s",
            sha[:12],
            target_branch or "?",
            path,
        )
        return True
    except OSError as exc:
        logger.error(
            "rollback_state: could not write %s (%s). "
            "Ensure /opt/meshpoint/data is owned by meshpoint:meshpoint.",
            path,
            exc,
        )
        return False


def clear_rollback_state(path: Path = DEFAULT_ROLLBACK_STATE_PATH) -> None:
    """Remove the rollback pointer after a successful roll-back."""
    try:
        path.unlink(missing_ok=True)
    except OSError as exc:
        logger.warning("rollback_state: could not clear %s: %s", path, exc)
