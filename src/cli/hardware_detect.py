"""Auto-detect Mesh Point hardware on a Raspberry Pi.

Probes for SPI concentrator devices, I2C carrier board signatures,
serial Meshtastic radios, and GPS UART to help the setup wizard
configure the right sources.
"""

from __future__ import annotations

import glob
import os
import subprocess
import time
from dataclasses import dataclass, field
from typing import Optional

CARRIER_SENSECAP_M1 = "sensecap_m1"
CARRIER_RAK = "rak"
CARRIER_UNKNOWN = "unknown"

_HARDWARE_DESCRIPTIONS = {
    CARRIER_SENSECAP_M1: "SenseCap M1 (WM1303)",
    CARRIER_RAK: "RAK2287 + Raspberry Pi 4",
    CARRIER_UNKNOWN: "SX1302/SX1303 + Raspberry Pi 4",
}


@dataclass
class GpsProbeResult:
    available: bool = False
    uart_path: str = "/dev/ttyAMA0"
    got_fix: bool = False
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    altitude: Optional[float] = None
    satellites: int = 0


@dataclass
class HardwareReport:
    spi_devices: list[str] = field(default_factory=list)
    serial_ports: list[str] = field(default_factory=list)
    meshcore_usb_candidates: list[str] = field(default_factory=list)
    gps: GpsProbeResult = field(default_factory=GpsProbeResult)
    concentrator_available: bool = False
    libloragw_installed: bool = False
    carrier_type: str = CARRIER_UNKNOWN
    hardware_description: str = _HARDWARE_DESCRIPTIONS[CARRIER_UNKNOWN]


def detect_all() -> HardwareReport:
    """Run all hardware probes and return a consolidated report."""
    report = HardwareReport()
    report.spi_devices = detect_spi_devices()
    report.serial_ports = detect_serial_ports()
    report.meshcore_usb_candidates = detect_meshcore_usb_candidates()
    report.libloragw_installed = check_libloragw()
    report.concentrator_available = (
        len(report.spi_devices) > 0 and report.libloragw_installed
    )
    report.carrier_type = detect_carrier_board()
    report.hardware_description = _HARDWARE_DESCRIPTIONS.get(
        report.carrier_type, _HARDWARE_DESCRIPTIONS[CARRIER_UNKNOWN]
    )
    report.gps = probe_gps()
    return report


def detect_spi_devices() -> list[str]:
    """Find SPI device nodes that could be an SX1302/SX1303 concentrator."""
    return sorted(glob.glob("/dev/spidev0.*"))


def detect_carrier_board() -> str:
    """Identify the carrier board by probing I2C for signature chips.

    SenseCap M1 has both an ATECC608 crypto chip at 0x60 AND a temperature
    sensor at 0x39.  RAK Pi HATs have an EEPROM at 0x50 (and sometimes
    0x60) but no temperature sensor.  Requiring both addresses avoids
    false positives.
    """
    try:
        result = subprocess.run(
            ["i2cdetect", "-y", "1"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode != 0:
            return CARRIER_UNKNOWN
        has_atecc = " 60 " in result.stdout or " 60\n" in result.stdout
        has_temp = " 39 " in result.stdout or " 39\n" in result.stdout
        if has_atecc and has_temp:
            return CARRIER_SENSECAP_M1
        return CARRIER_RAK
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return CARRIER_UNKNOWN


def detect_serial_ports() -> list[str]:
    """Find USB serial devices likely to be Meshtastic radios."""
    candidates = []
    for pattern in ["/dev/ttyACM*", "/dev/ttyUSB*"]:
        candidates.extend(glob.glob(pattern))
    return sorted(candidates)


def detect_meshcore_usb_candidates() -> list[str]:
    """Find USB serial ports that could be MeshCore devices.

    Returns all ttyUSB/ttyACM ports.  Actual MeshCore verification
    happens at runtime when the capture source connects.
    """
    candidates = []
    for pattern in ["/dev/ttyUSB*", "/dev/ttyACM*"]:
        candidates.extend(glob.glob(pattern))
    return sorted(candidates)


def check_libloragw() -> bool:
    """Check whether the patched libloragw.so is installed."""
    search_paths = [
        "/usr/local/lib/libloragw.so",
        "/usr/lib/libloragw.so",
        "./libloragw.so",
    ]
    return any(os.path.exists(p) for p in search_paths)


def probe_gps(
    uart_path: str = "/dev/ttyAMA0",
    timeout_seconds: float = 5.0,
) -> GpsProbeResult:
    """Attempt to read NMEA data from the GPS UART.

    Tries to get a GGA sentence with a valid fix within the timeout.
    Falls back to pyserial if asyncio serial is unavailable.
    """
    result = GpsProbeResult(uart_path=uart_path)

    if not os.path.exists(uart_path):
        return result

    try:
        import serial as pyserial

        ser = pyserial.Serial(uart_path, baudrate=9600, timeout=1.0)
        result.available = True

        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            line = ser.readline().decode("ascii", errors="ignore").strip()
            if line.startswith("$GPGGA") or line.startswith("$GNGGA"):
                _parse_gga(line, result)
                if result.got_fix:
                    break

        ser.close()
    except ImportError:
        if os.path.exists(uart_path):
            result.available = True
    except Exception:
        pass

    return result


def _parse_gga(sentence: str, result: GpsProbeResult) -> None:
    """Parse a GGA NMEA sentence and populate the probe result."""
    parts = sentence.split(",")
    if len(parts) < 10:
        return

    fix_quality = parts[6]
    if fix_quality == "" or fix_quality == "0":
        return

    try:
        result.latitude = _nmea_to_decimal(parts[2], parts[3])
        result.longitude = _nmea_to_decimal(parts[4], parts[5])
        result.got_fix = True

        if parts[7]:
            result.satellites = int(parts[7])
        if parts[9]:
            result.altitude = float(parts[9])
    except (ValueError, IndexError):
        pass


def _nmea_to_decimal(coord: str, direction: str) -> float:
    """Convert NMEA coordinate (DDMM.MMMM) to decimal degrees."""
    if not coord:
        raise ValueError("Empty coordinate")

    dot = coord.index(".")
    degrees = int(coord[: dot - 2])
    minutes = float(coord[dot - 2 :])
    decimal = degrees + minutes / 60.0

    if direction in ("S", "W"):
        decimal = -decimal

    return round(decimal, 6)


def print_report(report: HardwareReport) -> None:
    """Print a human-readable hardware detection summary."""
    print("\n  Hardware Detection Results")
    print("  " + "=" * 40)

    if report.spi_devices:
        print(f"  SPI devices:     {', '.join(report.spi_devices)}")
    else:
        print("  SPI devices:     none found")

    print(f"  libloragw.so:    {'installed' if report.libloragw_installed else 'NOT found'}")
    print(f"  Concentrator:    {'ready' if report.concentrator_available else 'not available'}")
    print(f"  Carrier board:   {report.hardware_description}")

    if report.serial_ports:
        print(f"  Serial ports:    {', '.join(report.serial_ports)}")
    else:
        print("  Serial ports:    none found")

    if report.meshcore_usb_candidates:
        print(f"  USB candidates:  {', '.join(report.meshcore_usb_candidates)}")
    else:
        print("  USB candidates:  none (MeshCore USB auto-detect disabled)")

    gps = report.gps
    if gps.available:
        if gps.got_fix:
            print(f"  GPS:             fix ({gps.latitude}, {gps.longitude}), "
                  f"{gps.satellites} satellites, alt {gps.altitude}m")
        else:
            print(f"  GPS:             UART present at {gps.uart_path}, no fix yet")
    else:
        print("  GPS:             not detected")

    print()
