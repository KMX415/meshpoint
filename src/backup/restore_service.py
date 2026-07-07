"""Validate backup uploads and launch detached restore."""

from __future__ import annotations

import hashlib
import logging
import re
import subprocess
import tarfile
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

from src.backup.manifest import FORMAT_VERSION, BackupManifest
from src.backup.paths import (
    MAX_UPLOAD_BYTES,
    launch_restore_finish_script,
    restore_finish_script,
    restore_incoming_dir,
)

logger = logging.getLogger(__name__)

_ALLOWED_PREFIXES = ("config/local.yaml", "data/")
_MANIFEST_NAME = "manifest.json"
_BUNDLE_DIR_PATTERN = re.compile(r"^meshpoint-backup-[a-zA-Z0-9_-]+-\d{8}T\d{6}Z$")


class RestoreValidationError(ValueError):
    """Raised when an uploaded archive fails validation."""


@dataclass(frozen=True)
class RestoreLaunchResult:
    """Outcome of scheduling a restore."""

    archive_path: Path
    stash_hint: str
    message: str


class BackupRestoreService:
    """Validate archives and spawn ``restore_finish.sh``."""

    def __init__(
        self,
        *,
        data_dir: Path,
        meshpoint_root: Path | None = None,
        finish_script: Path | None = None,
    ) -> None:
        self._data_dir = data_dir
        self._meshpoint_root = meshpoint_root
        self._finish_script = finish_script

    def validate_archive_bytes(self, payload: bytes) -> BackupManifest:
        if len(payload) > MAX_UPLOAD_BYTES:
            raise RestoreValidationError(
                f"archive exceeds {MAX_UPLOAD_BYTES} byte limit",
            )
        if len(payload) < 64:
            raise RestoreValidationError("archive is too small")

        with tempfile.TemporaryDirectory(prefix="meshpoint-restore-validate-") as tmp:
            archive_path = Path(tmp) / "upload.tar.gz"
            archive_path.write_bytes(payload)
            return self.validate_archive_path(archive_path)

    def validate_archive_path(self, archive_path: Path) -> BackupManifest:
        try:
            with tarfile.open(archive_path, "r:gz") as tar:
                members = tar.getmembers()
                bundle_prefix = self._resolve_bundle_prefix(members)
                manifest_member = self._find_member(
                    members,
                    f"{bundle_prefix}/{_MANIFEST_NAME}",
                )
                if manifest_member is None:
                    raise RestoreValidationError("manifest.json missing")

                manifest_file = tar.extractfile(manifest_member)
                if manifest_file is None:
                    raise RestoreValidationError("could not read manifest.json")
                manifest = BackupManifest.from_json(
                    manifest_file.read().decode("utf-8"),
                )
                self._validate_manifest_header(manifest)

                expected_paths = {entry.path for entry in manifest.entries}

                for member in members:
                    if not member.isfile():
                        continue
                    rel = self._member_archive_path(member, bundle_prefix)
                    if rel is None:
                        continue
                    if rel == _MANIFEST_NAME:
                        continue
                    if not self._is_allowed_member_path(rel):
                        raise RestoreValidationError(
                            f"disallowed archive path: {rel}",
                        )
                    if rel not in expected_paths:
                        raise RestoreValidationError(
                            f"unexpected file in archive: {rel}",
                        )

                for entry in manifest.entries:
                    member = self._find_member(
                        members,
                        f"{bundle_prefix}/{entry.path}",
                    )
                    if member is None:
                        raise RestoreValidationError(
                            f"manifest entry missing from archive: {entry.path}",
                        )
                    file_obj = tar.extractfile(member)
                    if file_obj is None:
                        raise RestoreValidationError(
                            f"could not read archive member: {entry.path}",
                        )
                    digest = hashlib.sha256(file_obj.read()).hexdigest()
                    if digest != entry.sha256:
                        raise RestoreValidationError(
                            f"checksum mismatch for {entry.path}",
                        )

                return manifest
        except tarfile.TarError as exc:
            raise RestoreValidationError(f"invalid tar archive: {exc}") from exc

    def save_validated_upload(
        self,
        payload: bytes,
        *,
        manifest: BackupManifest | None = None,
    ) -> Path:
        manifest = manifest or self.validate_archive_bytes(payload)
        incoming = restore_incoming_dir(self._data_dir)
        incoming.mkdir(parents=True, exist_ok=True)
        short_id = (manifest.device_id or "unknown")[:8]
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        dest = incoming / f"meshpoint-restore-{short_id}-{stamp}.tar.gz"
        dest.write_bytes(payload)
        return dest

    def launch_restore(self, archive_path: Path) -> RestoreLaunchResult:
        launcher = launch_restore_finish_script(self._meshpoint_root)
        if not launcher.is_file():
            raise FileNotFoundError(f"restore launcher not found: {launcher}")
        script = self._finish_script or restore_finish_script(self._meshpoint_root)
        if not script.is_file():
            raise FileNotFoundError(f"restore script not found: {script}")

        proc = subprocess.Popen(  # noqa: S603
            ["sudo", "/bin/bash", str(launcher), str(archive_path)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )
        self._raise_if_restore_launch_failed(proc)
        logger.info(
            "restore_finish launched pid=%s archive=%s",
            proc.pid,
            archive_path,
        )
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        return RestoreLaunchResult(
            archive_path=archive_path,
            stash_hint=f"data/pre-restore-stash-{stamp}",
            message="restore initiated; service will restart shortly",
        )

    @staticmethod
    def _raise_if_restore_launch_failed(proc: subprocess.Popen) -> None:
        """Sudo rejects unknown argv instantly; surface that before claiming success."""
        for _ in range(20):
            rc = proc.poll()
            if rc is None:
                return
            time.sleep(0.05)

        if proc.returncode == 0:
            return

        detail = ""
        if proc.stderr is not None:
            detail = proc.stderr.read().decode("utf-8", errors="replace").strip()
        message = detail or f"restore_finish exited with code {proc.returncode}"
        raise RestoreValidationError(message)

    @staticmethod
    def _validate_manifest_header(manifest: BackupManifest) -> None:
        if manifest.format_version != FORMAT_VERSION:
            raise RestoreValidationError(
                f"unsupported format_version {manifest.format_version}",
            )
        if not manifest.device_id:
            raise RestoreValidationError("manifest missing device_id")

    @staticmethod
    def _resolve_bundle_prefix(members: list[tarfile.TarInfo]) -> str:
        prefixes: set[str] = set()
        for member in members:
            parts = PurePosixPath(member.name).parts
            if not parts:
                continue
            prefixes.add(parts[0])
        if len(prefixes) != 1:
            raise RestoreValidationError("archive must contain one top-level folder")
        prefix = next(iter(prefixes))
        if not _BUNDLE_DIR_PATTERN.match(prefix):
            raise RestoreValidationError(f"unexpected bundle folder name: {prefix}")
        return prefix

    @staticmethod
    def _member_archive_path(
        member: tarfile.TarInfo,
        bundle_prefix: str,
    ) -> str | None:
        prefix = f"{bundle_prefix}/"
        if not member.name.startswith(prefix):
            return None
        rel = member.name[len(prefix):]
        if not rel or rel.endswith("/"):
            return None
        return rel

    @staticmethod
    def _find_member(
        members: list[tarfile.TarInfo],
        path: str,
    ) -> tarfile.TarInfo | None:
        for member in members:
            if member.name == path:
                return member
        return None

    @staticmethod
    def _is_allowed_member_path(path: str) -> bool:
        if path == _MANIFEST_NAME:
            return True
        if path == "config/local.yaml":
            return True
        if path.startswith("data/") and ".." not in path:
            return True
        return False
