"""Adafruit nRF52 serial DFU with 1200-baud touch and NDJSON streaming."""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import AsyncIterator, Optional

from src.api.firmware.esptool_stream import EspToolNdjsonStreamer
from src.api.firmware.nrf_dfu_binary import AdafruitNrfutilBinaryResolver

RECOVERY_HINT = (
    "Could not enter DFU over USB (1200-baud touch failed or bootloader "
    "did not respond). On-site recovery: double-press RESET for UF2/CDC, "
    "or hold BOOT/PROG while plugging USB, then retry Flash."
)

_PORT_WAIT_SECONDS = 15.0
_PORT_POLL_INTERVAL = 0.4


class AdafruitNrfDfuStreamer:
    """Build ``adafruit-nrfutil dfu serial`` argv and stream progress as NDJSON.

    Always uses ``--touch 1200`` and ``--singlebank`` so a healthy companion
    enters DFU without unplug or BOOT button (remote happy path).
    """

    def __init__(
        self,
        resolver: Optional[AdafruitNrfutilBinaryResolver] = None,
        streamer: Optional[EspToolNdjsonStreamer] = None,
    ) -> None:
        self._resolver = resolver or AdafruitNrfutilBinaryResolver()
        self._streamer = streamer or EspToolNdjsonStreamer()

    def build_argv(self, package: Path, port: str) -> list[str]:
        return [
            *self._resolver.resolve_argv(),
            "dfu",
            "serial",
            "--package",
            str(package),
            "-p",
            port,
            "-b",
            "115200",
            "--singlebank",
            "--touch",
            "1200",
        ]

    def missing_install_hint(self) -> Optional[str]:
        return self._resolver.missing_install_hint()

    def resolve_port_after_touch(
        self,
        preferred_port: str,
        *,
        vid: Optional[int] = None,
        pid: Optional[int] = None,
        timeout_s: float = _PORT_WAIT_SECONDS,
    ) -> Optional[str]:
        """Poll USB-serial until ``preferred_port`` (or VID/PID match) returns."""
        from src.hal.usb_classifier import list_serial_ports_with_stable_paths

        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            devices = list_serial_ports_with_stable_paths()
            aliases: set[str] = set()
            for dev in devices:
                if dev.vid is None:
                    continue
                values = {dev.device, dev.stable_path, dev.by_id, dev.by_path}
                aliases.update(v for v in values if v)
                if preferred_port in values:
                    return preferred_port
                if vid is not None and dev.vid == vid:
                    if pid is None or dev.pid == pid:
                        return dev.stable_path or dev.device
            if preferred_port in aliases:
                return preferred_port
            time.sleep(_PORT_POLL_INTERVAL)
        return None

    async def stream_dfu(
        self,
        package: Path,
        port: str,
        *,
        vid: Optional[int] = None,
        pid: Optional[int] = None,
    ) -> AsyncIterator[bytes]:
        """Emit step lines then stream adafruit-nrfutil NDJSON."""
        missing = self.missing_install_hint()
        if missing:
            yield self._streamer.ndjson({
                "type": "line", "stream": "stderr", "text": missing,
            })
            yield self._streamer.ndjson({
                "type": "result",
                "result": {"returncode": -1, "success": False, "error": missing},
            })
            return

        yield self._streamer.ndjson({
            "type": "line",
            "stream": "stdout",
            "text": "Entering DFU over USB (1200-baud touch)…",
        })
        yield self._streamer.ndjson({
            "type": "step", "step": "entering_dfu",
        })

        cmd = self.build_argv(package, port)
        success = False
        saw_no_data = False
        async for chunk in self._streamer.stream_subprocess(cmd):
            yield chunk
            try:
                event = json.loads(chunk)
            except json.JSONDecodeError:
                continue
            if event.get("type") == "line":
                text = (event.get("text") or "").lower()
                if "no data received" in text or "not in dfu" in text:
                    saw_no_data = True
            if event.get("type") == "result":
                success = bool((event.get("result") or {}).get("success"))

        if not success and saw_no_data:
            yield self._streamer.ndjson({
                "type": "line", "stream": "stderr", "text": RECOVERY_HINT,
            })

        if success and (vid is not None or pid is not None):
            loop = asyncio.get_running_loop()
            resolved = await loop.run_in_executor(
                None,
                lambda: self.resolve_port_after_touch(
                    port, vid=vid, pid=pid, timeout_s=5.0,
                ),
            )
            if resolved:
                yield self._streamer.ndjson({
                    "type": "step",
                    "step": "port_ready",
                    "port": resolved,
                })
