"""MeshCore companion release asset catalog (ESP merged.bin + nRF uf2/zip)."""

from __future__ import annotations

import re
import tempfile
from pathlib import Path
from typing import Optional

from src.api.firmware.github_http import GithubHttpClient

FLAVORS = ("usb", "ble")
MERGED_BIN_RE = re.compile(
    r"^(?P<board>.+)_companion_radio_(?P<flavor>usb|ble)-.+-merged\.bin$"
)
NRF_ASSET_RE = re.compile(
    r"^(?P<board>.+)_companion_radio_(?P<flavor>usb|ble)-.+\.(?P<ext>uf2|zip)$"
)
RELEASES_LIST_URL = (
    "https://api.github.com/repos/meshcore-dev/MeshCore/releases?per_page=20"
)


class MeshcoreFirmwareAssetCatalog:
    """Parse MeshCore companion releases into flashable board entries."""

    def __init__(
        self,
        http: Optional[GithubHttpClient] = None,
        cache_dir: Optional[Path] = None,
    ) -> None:
        self._http = http or GithubHttpClient()
        self._cache_dir = cache_dir or (
            Path(__file__).resolve().parents[3] / "data" / "meshcore-firmware"
        )

    def companion_releases_sync(self, limit: int = 10) -> list[dict]:
        releases = self._http.fetch_json_sync(RELEASES_LIST_URL)
        if not isinstance(releases, list):
            raise RuntimeError("Unexpected GitHub API response for MeshCore releases")
        companion = [
            r for r in releases if str(r.get("tag_name", "")).startswith("companion-")
        ]
        if not companion:
            raise RuntimeError("No companion-tagged MeshCore release found")
        return companion[:limit]

    def release_by_tag_sync(self, tag: str) -> dict:
        release = self._http.fetch_json_sync(
            f"https://api.github.com/repos/meshcore-dev/MeshCore/releases/tags/{tag}"
        )
        if not isinstance(release, dict) or not str(
            release.get("tag_name", "")
        ).startswith("companion-"):
            raise RuntimeError(f"'{tag}' is not a valid companion- release")
        return release

    def resolve_release_sync(self, tag: str) -> dict:
        if tag:
            return self.release_by_tag_sync(tag)
        return self.companion_releases_sync(1)[0]

    def board_list_from_release_sync(self, release: dict, flavor: str) -> list[dict]:
        if flavor not in FLAVORS:
            raise RuntimeError(f"Unknown flavor '{flavor}', expected one of {FLAVORS}")
        esp: dict[str, dict] = {}
        nrf: dict[str, dict] = {}
        for asset in release.get("assets", []):
            name = asset.get("name", "")
            m = MERGED_BIN_RE.match(name)
            if m and m.group("flavor") == flavor:
                board = m.group("board")
                esp[board] = {
                    "board": board,
                    "label": board.replace("_", " "),
                    "flash_method": "esptool",
                    "chip_family": "esp32",
                }
                continue
            m = NRF_ASSET_RE.match(name)
            if m and m.group("flavor") == flavor:
                board = m.group("board")
                nrf[board] = {
                    "board": board,
                    "label": board.replace("_", " "),
                    "flash_method": "nrf_dfu",
                    "chip_family": "nrf52",
                }
        # ESP merged.bin wins if a board somehow ships both.
        boards = {**nrf, **esp}
        return sorted(boards.values(), key=lambda b: b["label"].casefold())

    def flash_method_for_board(
        self, release: dict, board: str, flavor: str,
    ) -> str:
        for entry in self.board_list_from_release_sync(release, flavor):
            if entry["board"] == board:
                return entry["flash_method"]
        raise RuntimeError(
            f"Board '{board}' not found for flavor '{flavor}' in "
            f"{release.get('tag_name', 'this release')}"
        )

    def cache_dir_for(self, board: str, tag: str, flavor: str) -> Path:
        return self._cache_dir / board / tag / flavor

    def ensure_esptool_cached_sync(
        self, board: str, tag: str = "", flavor: str = "usb",
    ) -> dict:
        if flavor not in FLAVORS:
            raise RuntimeError(f"Unknown flavor '{flavor}', expected one of {FLAVORS}")
        release = self.resolve_release_sync(tag)
        resolved_tag = release.get("tag_name", "")
        cache_dir = self.cache_dir_for(board, resolved_tag, flavor)
        cache_dir.mkdir(parents=True, exist_ok=True)
        existing = list(
            cache_dir.glob(f"{board}_companion_radio_{flavor}-*-merged.bin")
        )
        if existing:
            return {
                "tag": resolved_tag,
                "flavor": flavor,
                "flash_method": "esptool",
                "merged_bin": existing[0],
            }

        prefix = f"{board}_companion_radio_{flavor}-"
        asset = next(
            (
                a for a in release.get("assets", [])
                if a["name"].startswith(prefix) and a["name"].endswith("-merged.bin")
            ),
            None,
        )
        if asset is None:
            raise RuntimeError(
                f"Could not find a '{prefix}*-merged.bin' asset in {resolved_tag}"
            )
        dest = cache_dir / asset["name"]
        self._download_asset(asset["browser_download_url"], dest, cache_dir)
        return {
            "tag": resolved_tag,
            "flavor": flavor,
            "flash_method": "esptool",
            "merged_bin": dest,
        }

    def ensure_nrf_cached_sync(
        self, board: str, tag: str = "", flavor: str = "usb",
    ) -> dict:
        if flavor not in FLAVORS:
            raise RuntimeError(f"Unknown flavor '{flavor}', expected one of {FLAVORS}")
        release = self.resolve_release_sync(tag)
        resolved_tag = release.get("tag_name", "")
        cache_dir = self.cache_dir_for(board, resolved_tag, flavor)
        cache_dir.mkdir(parents=True, exist_ok=True)

        zip_existing = list(
            cache_dir.glob(f"{board}_companion_radio_{flavor}-*.zip")
        )
        uf2_existing = list(
            cache_dir.glob(f"{board}_companion_radio_{flavor}-*.uf2")
        )
        if zip_existing:
            return {
                "tag": resolved_tag,
                "flavor": flavor,
                "flash_method": "nrf_dfu",
                "dfu_zip": zip_existing[0],
                "uf2": uf2_existing[0] if uf2_existing else None,
            }

        prefix = f"{board}_companion_radio_{flavor}-"
        zip_asset = next(
            (
                a for a in release.get("assets", [])
                if a["name"].startswith(prefix) and a["name"].endswith(".zip")
            ),
            None,
        )
        uf2_asset = next(
            (
                a for a in release.get("assets", [])
                if a["name"].startswith(prefix) and a["name"].endswith(".uf2")
            ),
            None,
        )
        if zip_asset is None:
            raise RuntimeError(
                f"Could not find a '{prefix}*.zip' DFU package in {resolved_tag}"
            )
        zip_dest = cache_dir / zip_asset["name"]
        self._download_asset(zip_asset["browser_download_url"], zip_dest, cache_dir)
        uf2_path = None
        if uf2_asset is not None:
            uf2_dest = cache_dir / uf2_asset["name"]
            self._download_asset(
                uf2_asset["browser_download_url"], uf2_dest, cache_dir,
            )
            uf2_path = uf2_dest
        return {
            "tag": resolved_tag,
            "flavor": flavor,
            "flash_method": "nrf_dfu",
            "dfu_zip": zip_dest,
            "uf2": uf2_path,
        }

    def ensure_board_firmware_cached_sync(
        self, board: str, tag: str = "", flavor: str = "usb",
    ) -> dict:
        release = self.resolve_release_sync(tag)
        method = self.flash_method_for_board(release, board, flavor)
        if method == "nrf_dfu":
            return self.ensure_nrf_cached_sync(board, tag=tag, flavor=flavor)
        return self.ensure_esptool_cached_sync(board, tag=tag, flavor=flavor)

    def _download_asset(self, url: str, dest: Path, cache_dir: Path) -> None:
        with tempfile.NamedTemporaryFile(
            suffix=dest.suffix, dir=cache_dir, delete=False,
        ) as tmp:
            tmp_path = Path(tmp.name)
        try:
            self._http.download_to_sync(url, tmp_path)
            tmp_path.rename(dest)
            dest.chmod(0o644)
        except BaseException:
            tmp_path.unlink(missing_ok=True)
            raise
