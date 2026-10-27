"""Unit tests for Configuration → Firmware flash helpers and routes.

Credit: javastraat/meshpoint firmware flash port (mocked GitHub / no hardware).
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.auth import dependencies as auth_deps
from src.api.auth.dependencies import SESSION_COOKIE_NAME
from src.api.auth.jwt_session import ROLE_ADMIN, ROLE_VIEWER, JwtSessionService
from src.api.firmware.esptool_binary import EspToolBinaryResolver
from src.api.firmware.esptool_stream import EspToolNdjsonStreamer
from src.api.routes import meshcore_firmware_routes as mc_routes
from src.api.routes import meshtastic_firmware_routes as mt_routes

_SECRET = "firmware-test-secret-" + "x" * 16


class TestFlashRequestDefaults(unittest.TestCase):
    def test_meshcore_erase_default_false(self):
        req = mc_routes.FlashRequest(board="Heltec_v3", port="/dev/ttyUSB0")
        self.assertFalse(req.erase_all)

    def test_meshtastic_erase_default_false(self):
        req = mt_routes.FlashRequest(board="heltec-v3", port="/dev/ttyUSB0")
        self.assertFalse(req.erase_all)


class TestMeshcoreBoardList(unittest.TestCase):
    def test_filters_flavor_and_merged_bin(self):
        release = {
            "tag_name": "companion-v1.16.0",
            "assets": [
                {
                    "name": "Heltec_v3_companion_radio_usb-abc-merged.bin",
                    "browser_download_url": "https://example/a",
                },
                {
                    "name": "Heltec_v3_companion_radio_ble-abc-merged.bin",
                    "browser_download_url": "https://example/b",
                },
                {
                    "name": "Heltec_v3_companion_radio_usb-abc.bin",
                    "browser_download_url": "https://example/c",
                },
            ],
        }
        usb = mc_routes._board_list_from_release_sync(release, "usb")
        ble = mc_routes._board_list_from_release_sync(release, "ble")
        self.assertEqual([b["board"] for b in usb], ["Heltec_v3"])
        self.assertEqual(usb[0]["flash_method"], "esptool")
        self.assertEqual([b["board"] for b in ble], ["Heltec_v3"])


class TestMeshcoreCompanionFilter(unittest.TestCase):
    def test_companion_releases_only(self):
        fake = [
            {"tag_name": "v1.0.0"},
            {"tag_name": "companion-v1.16.0", "published_at": "2026-01-01"},
            {"tag_name": "companion-v1.15.0", "published_at": "2025-12-01"},
        ]
        with patch.object(mc_routes._catalog._http, "fetch_json_sync", return_value=fake):
            out = mc_routes._companion_releases_sync(10)
        self.assertEqual(
            [r["tag_name"] for r in out],
            ["companion-v1.16.0", "companion-v1.15.0"],
        )


class TestEspToolHelpers(unittest.TestCase):
    def test_ndjson_round_trip(self):
        streamer = EspToolNdjsonStreamer()
        raw = streamer.ndjson({"type": "line", "text": "hi"})
        self.assertTrue(raw.endswith(b"\n"))
        self.assertEqual(json.loads(raw), {"type": "line", "text": "hi"})

    def test_resolver_falls_back_to_module_argv(self):
        resolver = EspToolBinaryResolver()
        with patch.object(Path, "is_file", return_value=False), patch(
            "src.api.firmware.esptool_binary.shutil.which", return_value=None,
        ), patch(
            "src.api.firmware.esptool_binary.sys.executable",
            "/opt/meshpoint/venv/bin/python",
        ):
            self.assertEqual(
                resolver.resolve_argv(),
                ["/opt/meshpoint/venv/bin/python", "-m", "esptool"],
            )
            self.assertEqual(resolver.resolve(), "esptool")

    def test_resolver_uses_venv_sibling_without_resolve(self):
        resolver = EspToolBinaryResolver()
        fake_python = Path("/opt/meshpoint/venv/bin/python")
        fake_esptool = Path("/opt/meshpoint/venv/bin/esptool")

        def is_file(self: Path) -> bool:
            return str(self) == str(fake_esptool)

        with patch("src.api.firmware.esptool_binary.sys.executable", str(fake_python)):
            with patch.object(Path, "is_file", is_file):
                self.assertEqual(resolver.resolve(), str(fake_esptool))
                self.assertEqual(resolver.resolve_argv(), [str(fake_esptool)])

    def test_write_flash_subcommand_is_underscore(self):
        from src.api.firmware.esptool_binary import WRITE_FLASH_SUBCOMMAND

        self.assertEqual(WRITE_FLASH_SUBCOMMAND, "write_flash")
        self.assertNotIn("-", WRITE_FLASH_SUBCOMMAND)

    def test_missing_hint_when_package_absent(self):
        resolver = EspToolBinaryResolver()

        def _no_esptool(name, *args, **kwargs):
            if name == "esptool" or (
                isinstance(name, str) and name.startswith("esptool")
            ):
                raise ImportError("no esptool")
            return __import__(name, *args, **kwargs)

        with patch.object(resolver, "resolve_path", return_value=None), patch(
            "builtins.__import__", side_effect=_no_esptool,
        ):
            hint = resolver.missing_install_hint()
        self.assertIsNotNone(hint)
        self.assertIn("pip install", hint)

    def test_erase_flag_omitted_from_cmd_when_false(self):
        from src.api.firmware.esptool_binary import WRITE_FLASH_SUBCOMMAND

        erase_all = False
        args = [
            WRITE_FLASH_SUBCOMMAND,
            *(["--erase-all"] if erase_all else []),
            "0x0",
            "fw.bin",
        ]
        self.assertNotIn("--erase-all", args)
        erase_all = True
        args = [
            WRITE_FLASH_SUBCOMMAND,
            *(["--erase-all"] if erase_all else []),
            "0x0",
            "fw.bin",
        ]
        self.assertIn("--erase-all", args)


class TestFirmwareRouteAuth(unittest.TestCase):
    def setUp(self):
        self.service = JwtSessionService(
            secret=_SECRET, expiry_minutes=60, session_version=1,
        )
        auth_deps.init_auth(self.service)
        self.app = FastAPI()
        self.app.include_router(mc_routes.router)
        self.app.include_router(mt_routes.router)
        self.client = TestClient(self.app)

    def tearDown(self):
        auth_deps.reset_auth()

    def _admin_cookie(self) -> None:
        token = self.service.issue("admin@test", ROLE_ADMIN)
        self.client.cookies.set(SESSION_COOKIE_NAME, token)

    def _viewer_cookie(self) -> None:
        token = self.service.issue("viewer@test", ROLE_VIEWER)
        self.client.cookies.set(SESSION_COOKIE_NAME, token)

    def test_releases_require_auth(self):
        res = self.client.get("/api/config/meshcore/firmware/releases")
        self.assertEqual(res.status_code, 401)

    def test_viewer_denied(self):
        self._viewer_cookie()
        res = self.client.get("/api/config/meshcore/firmware/releases")
        self.assertEqual(res.status_code, 403)

    def test_admin_releases_ok_with_mock(self):
        self._admin_cookie()
        fake = [{"tag_name": "companion-v1.16.0", "published_at": "2026-01-01"}]
        with patch.object(mc_routes._catalog._http, "fetch_json_sync", return_value=fake):
            res = self.client.get("/api/config/meshcore/firmware/releases")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["releases"][0]["tag"], "companion-v1.16.0")


class TestMeshcoreSourceConnectedProperty(unittest.TestCase):
    """Flash stream uses source.connected; SerialSource already exposes it."""

    def test_meshcore_usb_exposes_connected(self):
        from src.capture.meshcore_usb_source import MeshcoreUsbCaptureSource
        from src.config import MeshcoreUsbConfig

        source = MeshcoreUsbCaptureSource(MeshcoreUsbConfig())
        self.assertFalse(source.connected)
        source._connected = True
        self.assertTrue(source.connected)


if __name__ == "__main__":
    unittest.main()
