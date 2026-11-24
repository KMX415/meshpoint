"""Meshtastic release manifest catalog (ESP factory.bin + nRF ota.zip/uf2)."""

from __future__ import annotations

import json
import tempfile
import zipfile
from pathlib import Path
from typing import Optional

from src.api.firmware.github_http import GithubHttpClient

RELEASES_LATEST_URL = (
    "https://api.github.com/repos/meshtastic/firmware/releases/latest"
)
RELEASES_LIST_URL = (
    "https://api.github.com/repos/meshtastic/firmware/releases?per_page=10"
)
RELEASES_BY_TAG_URL = (
    "https://api.github.com/repos/meshtastic/firmware/releases/tags/{tag}"
)

_ESP_PLATFORMS = frozenset({"esp32", "esp32c3", "esp32c6", "esp32s3"})
_NRF_PLATFORMS = frozenset({"nrf52840"})


class MeshtasticFirmwareAssetCatalog:
    """Parse Meshtastic manifests into flash_method-tagged board lists."""

    def __init__(
        self,
        http: Optional[GithubHttpClient] = None,
        cache_dir: Optional[Path] = None,
    ) -> None:
        self._http = http or GithubHttpClient()
        self._cache_dir = cache_dir or (
            Path(__file__).resolve().parents[3] / "data" / "meshtastic-firmware"
        )

    def resolve_release_sync(self, tag: str) -> dict:
        if tag:
            return self._http.fetch_json_sync(RELEASES_BY_TAG_URL.format(tag=tag))
        return self._http.fetch_json_sync(RELEASES_LATEST_URL)

    def releases_sync(self, limit: int = 10) -> list[dict]:
        releases = self._http.fetch_json_sync(RELEASES_LIST_URL)
        if not isinstance(releases, list):
            raise RuntimeError("Unexpected GitHub API response for Meshtastic releases")
        return releases[:limit]

    def manifest_from_release_sync(self, release: dict) -> dict:
        assets = {
            a["name"]: a["browser_download_url"] for a in release.get("assets", [])
        }
        manifest_name = next(
            (n for n in assets if n.startswith("firmware-") and n.endswith(".json")),
            None,
        )
        if not manifest_name:
            raise RuntimeError("Could not find the firmware manifest in this release")
        with tempfile.NamedTemporaryFile(suffix=".json") as tmp:
            self._http.download_to_sync(assets[manifest_name], Path(tmp.name))
            return json.loads(Path(tmp.name).read_text())

    @staticmethod
    def method_for_platform(platform: str) -> tuple[str, str]:
        """Return ``(flash_method, chip_family)`` for a manifest platform."""
        if platform in _ESP_PLATFORMS:
            return "esptool", "esp32"
        if platform in _NRF_PLATFORMS:
            return "nrf_dfu", "nrf52"
        return "unsupported", platform

    def board_list_from_manifest_sync(self, manifest: dict) -> list[dict]:
        boards = []
        for t in manifest.get("targets", []):
            board = t.get("board")
            if not board:
                continue
            platform = t.get("platform") or ""
            method, family = self.method_for_platform(platform)
            boards.append({
                "board": board,
                "label": board.replace("-", " "),
                "flash_method": method,
                "chip_family": family,
                "platform": platform,
            })
        boards.sort(key=lambda b: b["label"].casefold())
        return boards

    def cache_dir_for(self, board: str, version: str) -> Path:
        return self._cache_dir / board / version

    def ensure_board_firmware_cached_sync(self, board: str, tag: str = "") -> dict:
        release = self.resolve_release_sync(tag)
        manifest = self.manifest_from_release_sync(release)
        assets = {
            a["name"]: a["browser_download_url"] for a in release.get("assets", [])
        }
        version = manifest.get("version") or release.get("tag_name", "").lstrip("v")
        target = next(
            (t for t in manifest.get("targets", []) if t.get("board") == board),
            None,
        )
        if target is None:
            raise RuntimeError(
                f"Board '{board}' not found in Meshtastic "
                f"{release.get('tag_name', 'this release')}"
            )
        platform = target["platform"]
        method, _family = self.method_for_platform(platform)
        if method == "unsupported":
            raise RuntimeError(
                f"Board '{board}' ({platform}) is not flashable from Meshpoint yet "
                "(UF2-only platforms are not supported in this release)."
            )
        if method == "nrf_dfu":
            return self._ensure_nrf_cached(
                board, version, platform, assets, release,
            )
        return self._ensure_esp_cached(
            board, version, platform, assets, release,
        )

    def _ensure_esp_cached(
        self,
        board: str,
        version: str,
        platform: str,
        assets: dict,
        release: dict,
    ) -> dict:
        cache_dir = self.cache_dir_for(board, version)
        mt_json_path = cache_dir / f"firmware-{board}-{version}.mt.json"
        factory_path = cache_dir / f"firmware-{board}-{version}.factory.bin"

        if mt_json_path.exists() and factory_path.exists():
            mt = json.loads(mt_json_path.read_text())
        else:
            zip_name = f"firmware-{platform}-{version}.zip"
            if zip_name not in assets:
                raise RuntimeError(
                    f"Could not find {zip_name} in the latest release assets"
                )
            cache_dir.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(suffix=".zip") as tmp_zip:
                self._http.download_to_sync(assets[zip_name], Path(tmp_zip.name))
                with zipfile.ZipFile(tmp_zip.name) as zf:
                    names = set(zf.namelist())
                    mt_name = f"firmware-{board}-{version}.mt.json"
                    factory_name = f"firmware-{board}-{version}.factory.bin"
                    if mt_name not in names or factory_name not in names:
                        raise RuntimeError(
                            f"Expected files for '{board}' missing from {zip_name}",
                        )
                    mt = json.loads(zf.read(mt_name))
                    mt_json_path.write_bytes(zf.read(mt_name))
                    factory_path.write_bytes(zf.read(factory_name))
                    mt_json_path.chmod(0o644)
                    factory_path.chmod(0o644)
                    spiffs_file = next(
                        (
                            f["name"]
                            for f in mt.get("files", [])
                            if f.get("part_name") == "spiffs"
                        ),
                        None,
                    )
                    if spiffs_file and spiffs_file in names:
                        spiffs_path = cache_dir / spiffs_file
                        spiffs_path.write_bytes(zf.read(spiffs_file))
                        spiffs_path.chmod(0o644)

        spiffs_file = next(
            (f["name"] for f in mt.get("files", []) if f.get("part_name") == "spiffs"),
            None,
        )
        littlefs_path = (cache_dir / spiffs_file) if spiffs_file else None
        spiffs_part = next(
            (p for p in mt.get("part", []) if p.get("name") == "spiffs"), None,
        )
        littlefs_offset = int(spiffs_part["offset"], 16) if spiffs_part else None
        return {
            "version": version,
            "mcu": mt["mcu"],
            "flash_method": "esptool",
            "factory_bin": factory_path,
            "littlefs_bin": (
                littlefs_path if (littlefs_path and littlefs_path.exists()) else None
            ),
            "littlefs_offset": littlefs_offset,
            "tag": release.get("tag_name", ""),
        }

    def _ensure_nrf_cached(
        self,
        board: str,
        version: str,
        platform: str,
        assets: dict,
        release: dict,
    ) -> dict:
        cache_dir = self.cache_dir_for(board, version)
        mt_json_path = cache_dir / f"firmware-{board}-{version}.mt.json"
        ota_path = cache_dir / f"firmware-{board}-{version}-ota.zip"
        uf2_path = cache_dir / f"firmware-{board}-{version}.uf2"

        if mt_json_path.exists() and ota_path.exists():
            mt = json.loads(mt_json_path.read_text())
        else:
            zip_name = f"firmware-{platform}-{version}.zip"
            if zip_name not in assets:
                raise RuntimeError(
                    f"Could not find {zip_name} in the latest release assets"
                )
            cache_dir.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(suffix=".zip") as tmp_zip:
                self._http.download_to_sync(assets[zip_name], Path(tmp_zip.name))
                with zipfile.ZipFile(tmp_zip.name) as zf:
                    names = set(zf.namelist())
                    mt_name = f"firmware-{board}-{version}.mt.json"
                    ota_name = f"firmware-{board}-{version}-ota.zip"
                    uf2_name = f"firmware-{board}-{version}.uf2"
                    if mt_name not in names or ota_name not in names:
                        raise RuntimeError(
                            f"Expected DFU files for '{board}' missing from {zip_name}",
                        )
                    mt = json.loads(zf.read(mt_name))
                    mt_json_path.write_bytes(zf.read(mt_name))
                    ota_path.write_bytes(zf.read(ota_name))
                    mt_json_path.chmod(0o644)
                    ota_path.chmod(0o644)
                    if uf2_name in names:
                        uf2_path.write_bytes(zf.read(uf2_name))
                        uf2_path.chmod(0o644)

        return {
            "version": version,
            "mcu": mt.get("mcu", "nrf52840"),
            "flash_method": "nrf_dfu",
            "dfu_zip": ota_path,
            "uf2": uf2_path if uf2_path.exists() else None,
            "requires_dfu": bool(mt.get("requiresDfu", True)),
            "tag": release.get("tag_name", ""),
        }
