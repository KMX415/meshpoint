"""Unit tests for nRF DFU catalog, upload store, and flash helpers."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.api.firmware.firmware_upload_store import FirmwareUploadStore
from src.api.firmware.meshcore_firmware_catalog import MeshcoreFirmwareAssetCatalog
from src.api.firmware.meshtastic_firmware_catalog import MeshtasticFirmwareAssetCatalog
from src.api.firmware.nrf_dfu_binary import AdafruitNrfutilBinaryResolver
from src.api.firmware.nrf_dfu_streamer import AdafruitNrfDfuStreamer, RECOVERY_HINT
from src.api.firmware.uf2_volume_flasher import Uf2VolumeFlasher
from src.api.routes import meshcore_firmware_routes as mc_routes


class TestMeshcoreNrfCatalog(unittest.TestCase):
    def test_lists_esp_and_nrf_with_methods(self):
        catalog = MeshcoreFirmwareAssetCatalog()
        release = {
            "tag_name": "companion-v1.17.1",
            "assets": [
                {
                    "name": "Heltec_v3_companion_radio_usb-abc-merged.bin",
                    "browser_download_url": "https://example/a",
                },
                {
                    "name": "Heltec_t096_companion_radio_usb-v1.17.1-abc.zip",
                    "browser_download_url": "https://example/b",
                },
                {
                    "name": "Heltec_t096_companion_radio_usb-v1.17.1-abc.uf2",
                    "browser_download_url": "https://example/c",
                },
            ],
        }
        boards = catalog.board_list_from_release_sync(release, "usb")
        by_board = {b["board"]: b for b in boards}
        self.assertEqual(by_board["Heltec_v3"]["flash_method"], "esptool")
        self.assertEqual(by_board["Heltec_t096"]["flash_method"], "nrf_dfu")
        self.assertEqual(by_board["Heltec_t096"]["chip_family"], "nrf52")

    def test_route_shim_includes_nrf(self):
        release = {
            "tag_name": "companion-v1.17.1",
            "assets": [
                {
                    "name": "Heltec_t096_companion_radio_usb-v1-d.zip",
                    "browser_download_url": "https://example/z",
                },
            ],
        }
        usb = mc_routes._board_list_from_release_sync(release, "usb")
        self.assertEqual(usb[0]["flash_method"], "nrf_dfu")


class TestMeshtasticPlatformMethods(unittest.TestCase):
    def test_platform_mapping(self):
        cat = MeshtasticFirmwareAssetCatalog
        self.assertEqual(cat.method_for_platform("esp32s3"), ("esptool", "esp32"))
        self.assertEqual(cat.method_for_platform("nrf52840"), ("nrf_dfu", "nrf52"))
        self.assertEqual(
            cat.method_for_platform("rp2040"), ("unsupported", "rp2040"),
        )

    def test_board_list_tags_methods(self):
        catalog = MeshtasticFirmwareAssetCatalog()
        manifest = {
            "targets": [
                {"board": "heltec-v3", "platform": "esp32s3"},
                {"board": "heltec-mesh-node-t114", "platform": "nrf52840"},
                {"board": "pico", "platform": "rp2040"},
            ],
        }
        boards = catalog.board_list_from_manifest_sync(manifest)
        by_board = {b["board"]: b for b in boards}
        self.assertEqual(by_board["heltec-v3"]["flash_method"], "esptool")
        self.assertEqual(
            by_board["heltec-mesh-node-t114"]["flash_method"], "nrf_dfu",
        )
        self.assertEqual(by_board["pico"]["flash_method"], "unsupported")


class TestFirmwareUploadStore(unittest.TestCase):
    def test_save_and_resolve_zip(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = FirmwareUploadStore(Path(tmp))
            upload_id = store.save("fw.zip", b"pkdata")
            path = store.resolve(upload_id)
            self.assertIsNotNone(path)
            self.assertEqual(path.read_bytes(), b"pkdata")
            self.assertEqual(path.suffix, ".zip")

    def test_rejects_bad_suffix(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = FirmwareUploadStore(Path(tmp))
            with self.assertRaises(ValueError):
                store.save("evil.exe", b"x")


class TestAdafruitNrfDfuStreamer(unittest.TestCase):
    def test_build_argv_includes_touch(self):
        streamer = AdafruitNrfDfuStreamer()
        with patch.object(
            AdafruitNrfutilBinaryResolver,
            "resolve_argv",
            return_value=["adafruit-nrfutil"],
        ):
            argv = streamer.build_argv(Path("/tmp/fw.zip"), "/dev/ttyACM0")
        self.assertIn("--touch", argv)
        self.assertIn("1200", argv)
        self.assertIn("--singlebank", argv)
        self.assertIn("dfu", argv)
        self.assertIn(RECOVERY_HINT, RECOVERY_HINT)


class TestUf2VolumeFlasher(unittest.TestCase):
    def test_missing_volume_raises(self):
        flasher = Uf2VolumeFlasher()
        with tempfile.TemporaryDirectory() as tmp:
            uf2 = Path(tmp) / "x.uf2"
            uf2.write_bytes(b"UF2")
            with patch.object(flasher, "find_uf2_mount", return_value=None):
                with self.assertRaises(RuntimeError) as ctx:
                    flasher.flash_uf2(uf2)
            self.assertIn("UF2", str(ctx.exception))

    def test_copies_when_mount_present(self):
        flasher = Uf2VolumeFlasher()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            mount = root / "BOOT"
            mount.mkdir()
            (mount / "INFO_UF2.TXT").write_text("UF2 Bootloader")
            uf2 = root / "app.uf2"
            uf2.write_bytes(b"UF2DATA")
            with patch.object(flasher, "find_uf2_mount", return_value=mount):
                dest = flasher.flash_uf2(uf2)
            self.assertTrue(dest.is_file())
            self.assertEqual(dest.read_bytes(), b"UF2DATA")


class TestCompanionReleasesPatchCatalog(unittest.TestCase):
    def test_companion_releases_via_catalog_http(self):
        fake = [
            {"tag_name": "v1.0.0"},
            {"tag_name": "companion-v1.16.0", "published_at": "2026-01-01"},
        ]
        with patch.object(mc_routes._catalog._http, "fetch_json_sync", return_value=fake):
            out = mc_routes._companion_releases_sync(10)
        self.assertEqual([r["tag_name"] for r in out], ["companion-v1.16.0"])


if __name__ == "__main__":
    unittest.main()
