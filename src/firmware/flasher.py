"""Async esptool subprocess runner for companion firmware flashes."""
from __future__ import annotations

import asyncio
import logging
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Awaitable, Callable

logger = logging.getLogger(__name__)

_port_locks: dict[str, asyncio.Lock] = {}


def get_port_lock(port: str) -> asyncio.Lock:
    if port not in _port_locks:
        _port_locks[port] = asyncio.Lock()
    return _port_locks[port]


@dataclass
class FlashJob:
    port: str
    baud: int
    offset: str
    bin_path: Path
    log_callback: Callable[[str], Awaitable[None]]


async def run_flash_job(job: FlashJob) -> bool:
    """Run esptool; stream stdout to log_callback. Caller holds port lock."""
    command = [
        sys.executable,
        "-m",
        "esptool",
        "--port",
        job.port,
        "--baud",
        str(job.baud),
        "write_flash",
        "-z",
        job.offset,
        str(job.bin_path),
    ]

    await job.log_callback(f"[flasher] {' '.join(command)}")

    try:
        proc = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        if proc.stdout is None:
            await job.log_callback("[flasher] ERROR: no subprocess stdout")
            return False

        async for raw in proc.stdout:
            line = raw.decode("utf-8", errors="replace").rstrip()
            if line:
                await job.log_callback(line)

        await proc.wait()
        success = proc.returncode == 0
        await job.log_callback(
            "[flasher] SUCCESS"
            if success
            else f"[flasher] FAILED (exit {proc.returncode})"
        )
        return success

    except FileNotFoundError:
        await job.log_callback(
            "[flasher] ERROR: esptool not found — "
            "install with: pip install esptool"
        )
        return False
    except Exception as exc:
        logger.exception("Flash job failed")
        await job.log_callback(f"[flasher] EXCEPTION: {exc}")
        return False
