"""Tests for restore archive validation."""

from __future__ import annotations

import hashlib
import io
import tarfile
import tempfile
import unittest
from pathlib import Path

from src.backup.manifest import FORMAT_VERSION, BackupFileEntry, BackupManifest
from src.backup.restore_service import BackupRestoreService, RestoreValidationError


def _build_archive(
    *,
    files: dict[str, bytes],
    manifest: BackupManifest,
    extra_members: tuple[tarfile.TarInfo, ...] = (),
    bundle_name: str = "meshpoint-backup-test0001-20260611T120000Z",
) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as tar:
        manifest_bytes = manifest.to_json().encode("utf-8")
        info = tarfile.TarInfo(name=f"{bundle_name}/manifest.json")
        info.size = len(manifest_bytes)
        tar.addfile(info, io.BytesIO(manifest_bytes))
        for rel_path, payload in files.items():
            info = tarfile.TarInfo(name=f"{bundle_name}/{rel_path}")
            info.size = len(payload)
            tar.addfile(info, io.BytesIO(payload))
        for member in extra_members:
            tar.addfile(member)
    return buffer.getvalue()


class TestBackupRestoreValidate(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.data_dir = Path(self.tmp.name) / "data"
        self.data_dir.mkdir()
        self.service = BackupRestoreService(data_dir=self.data_dir)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _valid_manifest(self) -> BackupManifest:
        local_bytes = b"device:\n  device_id: abc\n"
        digest = hashlib.sha256(local_bytes).hexdigest()
        return BackupManifest(
            format_version=FORMAT_VERSION,
            meshpoint_version="0.7.7",
            created_at="2026-06-11T12:00:00Z",
            device_id="abc",
            device_name="Test",
            entries=[
                BackupFileEntry(
                    path="config/local.yaml",
                    sha256=digest,
                    size_bytes=len(local_bytes),
                ),
            ],
            total_bytes=len(local_bytes),
        )

    def test_accepts_valid_archive(self) -> None:
        manifest = self._valid_manifest()
        local_bytes = b"device:\n  device_id: abc\n"
        payload = _build_archive(
            manifest=manifest,
            files={"config/local.yaml": local_bytes},
        )
        restored = self.service.validate_archive_bytes(payload)
        self.assertEqual(restored.device_id, "abc")

    def test_rejects_bad_checksum(self) -> None:
        manifest = self._valid_manifest()
        payload = _build_archive(
            manifest=manifest,
            files={"config/local.yaml": b"tampered"},
        )
        with self.assertRaises(RestoreValidationError):
            self.service.validate_archive_bytes(payload)

    def test_rejects_path_traversal(self) -> None:
        manifest = self._valid_manifest()
        buffer = io.BytesIO()
        bundle = "meshpoint-backup-test0001-20260611T120000Z"
        with tarfile.open(fileobj=buffer, mode="w:gz") as tar:
            evil = b"evil"
            info = tarfile.TarInfo(name=f"{bundle}/../escape.txt")
            info.size = len(evil)
            tar.addfile(info, io.BytesIO(evil))
            manifest_bytes = manifest.to_json().encode("utf-8")
            info = tarfile.TarInfo(name=f"{bundle}/manifest.json")
            info.size = len(manifest_bytes)
            tar.addfile(info, io.BytesIO(manifest_bytes))
        with self.assertRaises(RestoreValidationError):
            self.service.validate_archive_bytes(buffer.getvalue())

    def test_rejects_unsupported_format_version(self) -> None:
        manifest = self._valid_manifest()
        manifest.format_version = 99
        payload = _build_archive(
            manifest=manifest,
            files={"config/local.yaml": b"device:\n  device_id: abc\n"},
        )
        with self.assertRaises(RestoreValidationError):
            self.service.validate_archive_bytes(payload)

    def test_rejects_special_members(self) -> None:
        bundle = "meshpoint-backup-test0001-20260611T120000Z"
        for kind in (tarfile.SYMTYPE, tarfile.LNKTYPE, tarfile.FIFOTYPE,
                     tarfile.CHRTYPE, tarfile.BLKTYPE):
            with self.subTest(kind=kind):
                member = tarfile.TarInfo(name=f"{bundle}/data/special")
                member.type = kind
                member.linkname = f"{bundle}/config/local.yaml"
                payload = _build_archive(
                    manifest=self._valid_manifest(),
                    files={"config/local.yaml": b"device:\n  device_id: abc\n"},
                    extra_members=(member,),
                )
                with self.assertRaisesRegex(RestoreValidationError, "non-regular-file"):
                    self.service.validate_archive_bytes(payload)

    def test_accepts_directory_members(self) -> None:
        directory = tarfile.TarInfo(
            name="meshpoint-backup-test0001-20260611T120000Z/data"
        )
        directory.type = tarfile.DIRTYPE
        payload = _build_archive(
            manifest=self._valid_manifest(),
            files={"config/local.yaml": b"device:\n  device_id: abc\n"},
            extra_members=(directory,),
        )
        restored = self.service.validate_archive_bytes(payload)
        self.assertEqual(restored.device_id, "abc")


if __name__ == "__main__":
    unittest.main()
