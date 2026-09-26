"""Low-level hardware probes used by hardware_detect.

Kept separate so unit tests can mock SPI/subprocess without importing
the full detection report stack.
"""

from __future__ import annotations

import glob
import os
import re
import subprocess
from typing import Literal, Optional

ConcentratorChip = Literal["sx1302", "sx1303"]

_CHIP_VERSIONS: dict[int, ConcentratorChip] = {
    0x10: "sx1302",
    0x12: "sx1303",
}

_CHIP_ID_GLOBS = (
    "/opt/sx1302_hal/util_chip_id/chip_id",
    "/opt/sx1302_hal/chip_id",
    "/opt/sx1302_hal/**/chip_id",
)

_HAT_PRODUCT_PATH = "/proc/device-tree/hat/product"
_HAT_VENDOR_PATH = "/proc/device-tree/hat/vendor"


def probe_concentrator_chip(
    spi_path: str = "/dev/spidev0.0",
) -> Optional[ConcentratorChip]:
    """Read SX1302/SX1303 version register via chip_id when HAL is built.

    Returns None when no concentrator responds (0x00/0xFF, missing binary,
    or probe error). Requires libloragw build from install.sh on Gateway Pis.
    """
    binary = _find_chip_id_binary()
    if binary is None:
        return None

    try:
        result = subprocess.run(
            [binary, "-d", spi_path],
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None

    combined = f"{result.stdout or ''}\n{result.stderr or ''}"
    return _parse_chip_version(combined)


def detect_wismesh_hat() -> bool:
    """True when the Pi HAT EEPROM identifies RAK6421 / WisMesh."""
    product = _read_device_tree_string(_HAT_PRODUCT_PATH)
    vendor = _read_device_tree_string(_HAT_VENDOR_PATH)
    product_upper = (product or "").upper()
    vendor_upper = (vendor or "").upper()

    if "6421" in product_upper or "WISMESH" in product_upper:
        return True
    if "RAK" in vendor_upper and "6421" in product_upper:
        return True
    return False


def _find_chip_id_binary() -> Optional[str]:
    for path in _CHIP_ID_GLOBS:
        if "**" in path:
            matches = sorted(glob.glob(path, recursive=True))
            for match in matches:
                if os.path.isfile(match) and os.access(match, os.X_OK):
                    return match
            continue
        if os.path.isfile(path) and os.access(path, os.X_OK):
            return path
    return None


def _parse_chip_version(output: str) -> Optional[ConcentratorChip]:
    for match in re.finditer(r"0x([0-9a-fA-F]{2})", output):
        version = int(match.group(1), 16)
        chip = _CHIP_VERSIONS.get(version)
        if chip is not None:
            return chip
    return None


def _read_device_tree_string(path: str) -> Optional[str]:
    try:
        with open(path, "rb") as handle:
            raw = handle.read()
    except OSError:
        return None
    if not raw:
        return None
    text = raw.split(b"\x00", 1)[0].decode("ascii", errors="ignore").strip()
    return text or None
