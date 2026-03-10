"""Executor functions for MVP remote commands."""

from __future__ import annotations

import asyncio
import logging
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.version import __version__

logger = logging.getLogger(__name__)

MESHPOINT_SERVICE = "meshpoint"
MESHPOINT_DIR = "/opt/meshpoint"
GITHUB_REPO = "https://github.com/KMX415/meshpoint.git"


def execute_ping(_params: dict[str, Any]) -> dict[str, Any]:
    uptime = _read_uptime()
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "uptime_seconds": int(uptime),
        "version": __version__,
    }


def execute_get_status(_params: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": "running",
        "version": __version__,
        "uptime_seconds": int(_read_uptime()),
        "device_time": datetime.now(timezone.utc).isoformat(),
    }


def execute_get_metrics(_params: dict[str, Any]) -> dict[str, Any]:
    try:
        import psutil
    except ImportError:
        return {"error": "psutil not installed"}

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
        "system_uptime_seconds": int(_read_uptime()),
    }


def execute_get_logs(params: dict[str, Any]) -> dict[str, Any]:
    lines = min(int(params.get("lines", 50)), 200)
    try:
        result = subprocess.run(
            ["journalctl", "-u", MESHPOINT_SERVICE, "-n", str(lines), "--no-pager"],
            capture_output=True, text=True, timeout=10,
        )
        return {"lines": result.stdout.splitlines(), "count": lines}
    except FileNotFoundError:
        return {"error": "journalctl not available"}
    except subprocess.TimeoutExpired:
        return {"error": "Log retrieval timed out"}


def execute_restart_service(_params: dict[str, Any]) -> dict[str, Any]:
    """Restart the meshpoint systemd service.

    Runs in a detached subprocess so the response is sent
    before the service actually restarts.
    """
    logger.warning("Remote restart requested")
    subprocess.Popen(
        ["sudo", "systemctl", "restart", MESHPOINT_SERVICE],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    return {"message": "Restart initiated", "timestamp": datetime.now(timezone.utc).isoformat()}


async def execute_apply_update(params: dict[str, Any]) -> dict[str, Any]:
    """Pull a specific version from GitHub and apply it."""
    target_version = params.get("version")
    if not target_version:
        return {"error": "Missing 'version' parameter"}

    logger.warning("Remote update requested: target=%s current=%s", target_version, __version__)

    try:
        proc = await asyncio.create_subprocess_exec(
            "git", "fetch", "--tags", cwd=MESHPOINT_DIR,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        await proc.wait()

        proc = await asyncio.create_subprocess_exec(
            "git", "checkout", f"v{target_version}", cwd=MESHPOINT_DIR,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()
        if proc.returncode != 0:
            return {"error": f"Checkout failed: {stderr.decode().strip()}"}

        copy_dirs = ["src", "frontend", "config", "scripts"]
        for dirname in copy_dirs:
            src = Path(MESHPOINT_DIR) / dirname
            if src.exists():
                subprocess.run(
                    ["sudo", "cp", "-r", str(src) + "/", f"/opt/meshpoint/{dirname}/"],
                    check=True, timeout=30,
                )

        subprocess.run(
            ["sudo", "pip", "install", "-r", "/opt/meshpoint/requirements.txt"],
            capture_output=True, timeout=120,
        )

        subprocess.Popen(
            ["sudo", "systemctl", "restart", MESHPOINT_SERVICE],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )

        return {
            "message": f"Update to v{target_version} applied, restarting",
            "previous_version": __version__,
            "target_version": target_version,
        }
    except Exception as exc:
        logger.exception("Update failed")
        return {"error": str(exc)}


def _read_uptime() -> float:
    try:
        return float(Path("/proc/uptime").read_text().split()[0])
    except (FileNotFoundError, ValueError, OSError, IndexError):
        return 0.0


def _read_cpu_temp() -> float | None:
    try:
        return int(Path("/sys/class/thermal/thermal_zone0/temp").read_text().strip()) / 1000.0
    except (FileNotFoundError, ValueError, OSError):
        return None
