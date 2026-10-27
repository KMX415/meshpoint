"""Best-effort host health for the hosted node's ``/page/info.mu``.

All reads are plain ``/proc`` / ``/sys`` / ``shutil`` -- no ``psutil``, no
subprocess -- and every field is ``None`` when it can't be read (a
non-Linux dev box, a container without the thermal zone, ...). Nothing
here is sensitive: model, temperature, load, free space are the kind of
thing NomadNet nodes routinely publish.

FastAPI-free; the route/stats layer just merges the dict in.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path


def _pi_model() -> str | None:
    # /proc/device-tree/model is NUL-terminated; /proc/cpuinfo "Model:" is
    # the fallback on kernels/boards without the device-tree entry.
    try:
        m = Path("/proc/device-tree/model").read_text(errors="replace").strip("\x00").strip()
        if m:
            return m
    except OSError:
        pass
    try:
        for line in Path("/proc/cpuinfo").read_text().splitlines():
            if line.startswith("Model") and ":" in line:
                return line.split(":", 1)[1].strip() or None
    except OSError:
        pass
    return None


def _cpu_temp_c() -> float | None:
    try:
        milli = int(Path("/sys/class/thermal/thermal_zone0/temp").read_text().strip())
        return round(milli / 1000.0, 1)
    except (OSError, ValueError):
        return None


def _load_1m() -> float | None:
    try:
        return round(os.getloadavg()[0], 2)
    except (OSError, AttributeError):
        return None


def _mem_mb() -> tuple[int, int] | None:
    try:
        fields = {}
        for line in Path("/proc/meminfo").read_text().splitlines():
            k, _, rest = line.partition(":")
            fields[k.strip()] = int(rest.strip().split()[0])  # kB
        total = fields["MemTotal"] // 1024
        avail = fields.get("MemAvailable", fields.get("MemFree", 0)) // 1024
        return total - avail, total
    except (OSError, ValueError, KeyError, IndexError):
        return None


def _disk_gb() -> tuple[float, float] | None:
    try:
        u = shutil.disk_usage("/")
        return round(u.free / 1024**3, 1), round(u.total / 1024**3, 1)
    except OSError:
        return None


def read_host() -> dict:
    """``{pi_model, cpu_temp_c, load_1m, mem_used_mb, mem_total_mb,
    disk_free_gb, disk_total_gb}`` -- any value may be ``None``."""
    mem = _mem_mb()
    disk = _disk_gb()
    return {
        "pi_model": _pi_model(),
        "cpu_temp_c": _cpu_temp_c(),
        "load_1m": _load_1m(),
        "mem_used_mb": mem[0] if mem else None,
        "mem_total_mb": mem[1] if mem else None,
        "disk_free_gb": disk[0] if disk else None,
        "disk_total_gb": disk[1] if disk else None,
    }
