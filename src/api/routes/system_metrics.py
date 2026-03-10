"""System-level hardware metrics for the Mesh Point host."""

from __future__ import annotations

import shutil
from pathlib import Path

from fastapi import APIRouter

router = APIRouter(prefix="/api/device", tags=["device"])


def _read_cpu_temp() -> float | None:
    """Read CPU temperature from the thermal zone (Linux/RPi)."""
    thermal = Path("/sys/class/thermal/thermal_zone0/temp")
    try:
        return int(thermal.read_text().strip()) / 1000.0
    except (FileNotFoundError, ValueError, OSError):
        return None


def _read_uptime_seconds() -> float:
    """Read system uptime from /proc/uptime (Linux)."""
    try:
        return float(Path("/proc/uptime").read_text().split()[0])
    except (FileNotFoundError, ValueError, OSError, IndexError):
        return 0.0


@router.get("/metrics")
async def system_metrics():
    import psutil

    mem = psutil.virtual_memory()
    disk = shutil.disk_usage("/")
    cpu_temp = _read_cpu_temp()

    return {
        "cpu_percent": psutil.cpu_percent(interval=0.5),
        "memory_percent": mem.percent,
        "memory_used_mb": round(mem.used / (1024 * 1024)),
        "memory_total_mb": round(mem.total / (1024 * 1024)),
        "disk_percent": round(disk.used / disk.total * 100, 1),
        "disk_used_gb": round(disk.used / (1024 ** 3), 1),
        "disk_total_gb": round(disk.total / (1024 ** 3), 1),
        "cpu_temp_c": round(cpu_temp, 1) if cpu_temp is not None else None,
        "system_uptime_seconds": int(_read_uptime_seconds()),
    }
