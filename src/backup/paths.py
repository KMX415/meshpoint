"""Path resolution helpers for backup and restore."""

from __future__ import annotations

import os
import re
from pathlib import Path

from src.config import _get_local_yaml_path

_EXCLUDED_DATA_DIR_PATTERN = re.compile(
    r"^(restore-incoming|backup-staging|pre-restore-stash-)"
)

MAX_UPLOAD_BYTES = 500 * 1024 * 1024


def resolve_meshpoint_root() -> Path:
    """Return the Meshpoint install root (``MESHPOINT_DIR`` or cwd)."""
    return Path(os.environ.get("MESHPOINT_DIR", ".")).resolve()


def resolve_local_config_path() -> Path:
    """Resolved ``local.yaml`` path (honours ``CONCENTRATOR_CONFIG``)."""
    return _get_local_yaml_path()


def resolve_data_dir(database_path: str) -> Path:
    """Parent directory of the SQLite database file."""
    return Path(database_path).resolve().parent


def is_excluded_data_relative(relative_parts: tuple[str, ...]) -> bool:
    """True when a ``data/`` subtree should not be included in backups."""
    if not relative_parts:
        return False
    head = relative_parts[0]
    return bool(_EXCLUDED_DATA_DIR_PATTERN.match(head))


def restore_finish_script(meshpoint_root: Path | None = None) -> Path:
    root = meshpoint_root or resolve_meshpoint_root()
    return root / "scripts" / "restore_finish.sh"


def launch_restore_finish_script(meshpoint_root: Path | None = None) -> Path:
    root = meshpoint_root or resolve_meshpoint_root()
    return root / "scripts" / "launch_restore_finish.sh"


def restore_incoming_dir(data_dir: Path) -> Path:
    return data_dir / "restore-incoming"
