"""Low-level hardware probes used by hardware_detect.

Kept separate so unit tests can mock SPI/subprocess without importing
the full detection report stack.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Literal, Optional

ConcentratorChip = Literal["sx1302", "sx1303"]

_CHIP_VERSIONS: dict[int, ConcentratorChip] = {
    0x10: "sx1302",
    0x12: "sx1303",
}

_HAL_PATHS = ("/usr/local/lib/libloragw.so", "/usr/lib/libloragw.so", "./libloragw.so")
_RESET_SCRIPT = Path(__file__).resolve().parents[2] / "scripts/reset_concentrator.sh"

# Run in a child process so a HAL fault or timeout cannot strand the wizard.
# lgw_connect reads the version register; no lgw_start, RF configuration or TX.
_VERSION_PROBE = """
import ctypes, sys
hal = ctypes.CDLL(sys.argv[1])
hal.lgw_connect.argtypes = [ctypes.c_int, ctypes.c_char_p]
hal.lgw_connect.restype = ctypes.c_int
hal.lgw_disconnect.argtypes = []
hal.lgw_disconnect.restype = ctypes.c_int
try:
    rc = hal.lgw_connect(0, sys.argv[2].encode())
finally:
    close_rc = hal.lgw_disconnect()
sys.exit(0 if rc == 0 and close_rc == 0 else 1)
"""

class HardwareProbeError(RuntimeError):
    """Detection could not complete; this is not evidence of absent hardware."""

_HAT_PRODUCT_PATH = "/proc/device-tree/hat/product"
_HAT_VENDOR_PATH = "/proc/device-tree/hat/vendor"


def probe_concentrator_chip(
    spi_path: str = "/dev/spidev0.0",
) -> Optional[ConcentratorChip]:
    """Reset an idle gateway and read its version, without starting RF."""
    library = next((str(Path(p).resolve()) for p in _HAL_PATHS if os.path.isfile(p)), None)
    if library is None:
        raise HardwareProbeError("HAL library missing; complete scripts/install.sh first.")
    if not _RESET_SCRIPT.is_file():
        raise HardwareProbeError("Meshpoint reset helper missing; repair the installation.")
    try:
        state = subprocess.run(
            ["systemctl", "show", "meshpoint", "--property=ActiveState", "--value"],
            capture_output=True, text=True, timeout=5,
        )
        if state.returncode != 0 or state.stdout.strip() not in {"inactive", "failed"}:
            raise HardwareProbeError("Stop meshpoint before hardware detection (sudo systemctl stop meshpoint).")
        try:
            reset = subprocess.run(
                ["bash", "-e", str(_RESET_SCRIPT)],
                capture_output=True, text=True, timeout=10,
            )
            if reset.returncode != 0:
                raise HardwareProbeError("Concentrator reset failed; check GPIO tools and permissions.")
            result = subprocess.run(
                [sys.executable, "-c", _VERSION_PROBE, library, spi_path],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode != 0:
                raise HardwareProbeError("HAL version read failed; check SPI permissions and hardware.")
            output = result.stdout + "\n" + result.stderr
            if not re.search(r"chip version is 0x[0-9a-f]{2}\b", output, re.I):
                raise HardwareProbeError("HAL did not report a chip version; check the installed HAL build.")
            chip = _parse_chip_version(output)
            if chip is None:
                raise HardwareProbeError("No supported chip version returned; check power, reset wiring and SPI.")
            return chip
        finally:
            hold = subprocess.run(
                ["bash", "-e", str(_RESET_SCRIPT), "--hold"],
                capture_output=True, text=True, timeout=10,
            )
            if hold.returncode != 0:
                raise HardwareProbeError("Could not hold concentrator in reset after detection; check GPIO tools.")
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise HardwareProbeError("Hardware detection could not complete; check HAL, GPIO tools and permissions.") from exc


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


def _parse_chip_version(output: str) -> Optional[ConcentratorChip]:
    for match in re.finditer(r"(?:chip version is|concentrator version:)\s*0x([0-9a-f]{2})\b", output, re.I):
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
