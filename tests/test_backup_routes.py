"""Route-level coverage for backup download and restore."""

from __future__ import annotations

import hashlib
import io
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.audit import AuditLogWriter
from src.api.audit import dependencies as audit_deps
from src.api.auth import dependencies as auth_deps
from src.api.auth.jwt_session import JwtSessionService
from src.api.routes import backup_routes
from src.backup.archive_builder import BackupArchiveBuilder
from src.backup.manifest import FORMAT_VERSION, BackupFileEntry, BackupManifest
from src.config import AppConfig

_SECRET = "backup-routes-secret-" + "b" * 32


class TestBackupRoutes(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.config_dir = self.root / "config"
        self.data_dir = self.root / "data"
        self.config_dir.mkdir()
        self.data_dir.mkdir()
        (self.config_dir / "local.yaml").write_text(
            "device:\n  device_id: route-test-id\n  device_name: Route Test\n",
            encoding="utf-8",
        )
        (self.data_dir / "keys.yaml").write_text("private_key: aa\n", encoding="utf-8")

        self.config = AppConfig()
        self.config.device.device_id = "route-test-id"
        self.config.device.device_name = "Route Test"
        self.config.storage.database_path = str(self.data_dir / "concentrator.db")

        backup_routes.init_routes(self.config)
        self.audit = AuditLogWriter(log_path=self.data_dir / "admin_audit.jsonl")
        self.jwt = JwtSessionService(_SECRET, expiry_minutes=60, session_version=1)
        auth_deps.init_auth(self.jwt)
        audit_deps.init_audit(self.audit)

        app = FastAPI()
        app.include_router(backup_routes.router)
        self.client = TestClient(app)
        self.admin_token = self.jwt.issue("admin", "admin")
        self.viewer_token = self.jwt.issue("viewer", "viewer")

    def tearDown(self) -> None:
        backup_routes.reset_routes()
        auth_deps.reset_auth()
        audit_deps.reset_audit()
        self.tmp.cleanup()

    def test_status_requires_admin(self) -> None:
        response = self.client.get("/api/system/backup/status")
        self.assertEqual(response.status_code, 401)

        self.client.cookies.set("meshpoint_session", self.viewer_token)
        response = self.client.get("/api/system/backup/status")
        self.assertEqual(response.status_code, 403)

    def test_status_returns_device_summary(self) -> None:
        self.client.cookies.set("meshpoint_session", self.admin_token)
        with mock.patch(
            "src.api.routes.backup_routes.resolve_local_config_path",
            return_value=self.config_dir / "local.yaml",
        ), mock.patch(
            "src.api.routes.backup_routes.resolve_data_dir",
            return_value=self.data_dir,
        ):
            response = self.client.get("/api/system/backup/status")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["device_id"], "route-test-id")
        self.assertIn("config/local.yaml", body["includes"][0])

    def test_download_returns_attachment(self) -> None:
        self.client.cookies.set("meshpoint_session", self.admin_token)
        fake_result = BackupArchiveBuilder(
            meshpoint_root=self.root,
            local_config_path=self.config_dir / "local.yaml",
            data_dir=self.data_dir,
            database_path=str(self.data_dir / "concentrator.db"),
            device_id="route-test-id",
            device_name="Route Test",
        ).build()

        try:
            with mock.patch(
                "src.api.routes.backup_routes.BackupArchiveBuilder",
            ) as builder_cls:
                builder_cls.return_value.build.return_value = fake_result
                response = self.client.get("/api/system/backup/download")

            self.assertEqual(response.status_code, 200)
            self.assertIn("application/gzip", response.headers.get("content-type", ""))
            self.assertIn(
                "meshpoint-backup",
                response.headers.get("content-disposition", ""),
            )
        finally:
            try:
                fake_result.archive_path.unlink(missing_ok=True)
            except PermissionError:
                pass

    def test_restore_accepts_valid_upload(self) -> None:
        local_bytes = (self.config_dir / "local.yaml").read_bytes()
        digest = hashlib.sha256(local_bytes).hexdigest()
        manifest = BackupManifest(
            format_version=FORMAT_VERSION,
            meshpoint_version="0.7.7",
            created_at="2026-06-11T12:00:00Z",
            device_id="route-test-id",
            device_name="Route Test",
            entries=[
                BackupFileEntry(
                    path="config/local.yaml",
                    sha256=digest,
                    size_bytes=len(local_bytes),
                ),
            ],
            total_bytes=len(local_bytes),
        )
        buffer = io.BytesIO()
        bundle = "meshpoint-backup-route0001-20260611T120000Z"
        with tarfile.open(fileobj=buffer, mode="w:gz") as tar:
            for rel_path, payload in {
                "manifest.json": manifest.to_json().encode("utf-8"),
                "config/local.yaml": local_bytes,
            }.items():
                info = tarfile.TarInfo(name=f"{bundle}/{rel_path}")
                info.size = len(payload)
                tar.addfile(info, io.BytesIO(payload))

        self.client.cookies.set("meshpoint_session", self.admin_token)
        with mock.patch(
            "src.api.routes.backup_routes.BackupRestoreService.launch_restore",
        ) as launch:
            launch.return_value = mock.Mock(
                message="restore initiated",
                stash_hint="data/pre-restore-stash-test",
            )
            response = self.client.post(
                "/api/system/backup/restore",
                content=buffer.getvalue(),
                headers={"Content-Type": "application/gzip"},
            )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["success"])
        launch.assert_called_once()


if __name__ == "__main__":
    unittest.main()
