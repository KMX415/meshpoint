"""USB serial port classification by USB VID/PID.

Hardware-facts module shared by:
- ``src.capture.meshcore_usb_detect`` -- skip GPS sticks during MeshCore probing
- ``src.hal.location.factory`` (planned) -- locate GPS sticks for gpsd / uart

The classification table is intentionally small and conservative: only
hardware we have confirmed in the lab gets a known class. Everything else
falls through as ``UNKNOWN`` so existing behavior (probe-and-see) is
preserved.

Hardware confirmed (2026-05-30 on .141):

    0x1546:0x01a7  u-blox 7  (bare USB stick, VFAN puck) -- GPS_KNOWN
    0x1546:0x01a8  u-blox 8  (bare USB stick)            -- GPS_KNOWN
    0x10c4:0xea60  Silicon Labs CP210x (RAK Hotspot V2 SX1302 concentrator
                   AND Heltec V3 / V4 MeshCore companions)  -- AMBIGUOUS

The CP210x VID is shared between the on-board concentrator UART and the
ESP32-S3 MeshCore companion, so we do *not* pre-classify it. The existing
MeshCore handshake probe is the right disambiguator there.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_BY_ID_DIR = Path("/dev/serial/by-id")
_BY_PATH_DIR = Path("/dev/serial/by-path")


class PortClass(str, Enum):
    """Coarse classification of a USB serial port by its USB descriptor."""

    GPS_KNOWN = "gps_known"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class PortInfo:
    """Snapshot of a single USB serial port and its classification."""

    device: str
    vid: Optional[int]
    pid: Optional[int]
    manufacturer: Optional[str]
    product: Optional[str]
    port_class: PortClass


class UsbPortClassifier:
    """Classify USB serial ports by VID using a small static table.

    One instance per call site is fine; the classifier is stateless and
    cheap to construct. It re-enumerates ports on every call so a freshly
    plugged stick is picked up without restarting the process.
    """

    # VID -> PortClass. Populated from confirmed hardware only.
    _VID_TABLE: dict[int, PortClass] = {
        0x1546: PortClass.GPS_KNOWN,  # u-blox AG (all u-blox 7/8 USB receivers)
    }

    def classify(self, vid: Optional[int]) -> PortClass:
        """Return the class for *vid*, or ``UNKNOWN`` if not in the table."""
        if vid is None:
            return PortClass.UNKNOWN
        return self._VID_TABLE.get(vid, PortClass.UNKNOWN)

    def list_ports(self) -> list[PortInfo]:
        """Enumerate available USB serial ports with classification.

        Returns an empty list (with a debug log) if ``pyserial`` is not
        available, so callers can fall through to legacy glob-based
        discovery without crashing.
        """
        try:
            from serial.tools import list_ports
        except ImportError:
            logger.debug(
                "pyserial not available -- USB classification disabled"
            )
            return []

        infos: list[PortInfo] = []
        for entry in list_ports.comports():
            infos.append(
                PortInfo(
                    device=entry.device,
                    vid=entry.vid,
                    pid=entry.pid,
                    manufacturer=entry.manufacturer,
                    product=entry.product,
                    port_class=self.classify(entry.vid),
                )
            )
        return infos

    def known_gps_devices(self) -> list[str]:
        """Device paths whose VID matches a known GPS receiver."""
        return [
            info.device
            for info in self.list_ports()
            if info.port_class is PortClass.GPS_KNOWN
        ]


def _resolve_symlinks(directory: Path) -> dict[str, str]:
    """Map real device path -> first symlink name pointing at it."""
    result: dict[str, str] = {}
    if not directory.is_dir():
        return result
    for entry in sorted(directory.iterdir()):
        try:
            target = os.path.realpath(entry)
        except OSError:
            continue
        result.setdefault(target, str(entry))
    return result


@dataclass(frozen=True)
class StablePortInfo:
    """One USB-serial device with a recommended stable pin path."""

    device: str
    stable_path: str
    by_id: Optional[str]
    by_path: Optional[str]
    description: str
    vid: Optional[int]
    pid: Optional[int]


def list_serial_ports_with_stable_paths() -> list[StablePortInfo]:
    """Enumerate ports for the dashboard picker (by-path > by-id > device)."""
    classifier = UsbPortClassifier()
    by_id = _resolve_symlinks(_BY_ID_DIR)
    by_path = _resolve_symlinks(_BY_PATH_DIR)

    ports: list[StablePortInfo] = []
    for info in classifier.list_ports():
        try:
            real = os.path.realpath(info.device)
        except OSError:
            real = info.device
        id_path = by_id.get(real)
        path_path = by_path.get(real)
        stable = path_path or id_path or info.device
        description = (
            " ".join(p for p in (info.manufacturer, info.product) if p)
            or info.device
        )
        ports.append(
            StablePortInfo(
                device=info.device,
                stable_path=stable,
                by_id=id_path,
                by_path=path_path,
                description=description,
                vid=info.vid,
                pid=info.pid,
            )
        )
    return ports


def should_skip_for_meshcore_probe(port: str) -> bool:
    """True when *port* is a known GPS device and must not be MeshCore-probed.

    Probing a GPS stick at 115200 baud blocks for the full handshake
    timeout (5 s) and briefly grabs the device, which can disrupt
    gpsd's hold on it. Skipping is cheap and safe.
    """
    classifier = UsbPortClassifier()
    for info in classifier.list_ports():
        if info.device == port and info.port_class is PortClass.GPS_KNOWN:
            return True
    return False
