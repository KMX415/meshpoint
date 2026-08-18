"""Copy a UF2 image onto an Adafruit-style bootloader mass-storage volume."""

from __future__ import annotations

import logging
import shutil
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_UF2_MOUNT_ROOTS = (
    Path("/media"),
    Path("/run/media"),
    Path("/mnt"),
)
_UF2_MARKERS = ("INFO_UF2.TXT", "CURRENT.UF2", "INDEX.HTM")


class Uf2VolumeFlasher:
    """Find a UF2 bootloader volume and copy ``.uf2`` firmware onto it."""

    def find_uf2_mount(self) -> Optional[Path]:
        for root in _UF2_MOUNT_ROOTS:
            if not root.is_dir():
                continue
            for path in root.rglob("*"):
                if not path.is_dir():
                    continue
                if any((path / marker).is_file() for marker in _UF2_MARKERS):
                    return path
        return None

    def flash_uf2(self, uf2_path: Path, dest_dir: Optional[Path] = None) -> Path:
        """Copy ``uf2_path`` onto a UF2 volume. Raises ``RuntimeError`` if none."""
        if not uf2_path.is_file():
            raise RuntimeError(f"UF2 file not found: {uf2_path}")
        mount = dest_dir or self.find_uf2_mount()
        if mount is None:
            raise RuntimeError(
                "No UF2 bootloader volume mounted. Double-press RESET on the "
                "board so a USB drive appears, then retry."
            )
        dest = mount / uf2_path.name
        shutil.copy2(uf2_path, dest)
        logger.info("Copied %s to UF2 volume %s", uf2_path.name, mount)
        # Board usually remounts/disconnects after copy; brief settle.
        time.sleep(1.0)
        return dest
