"""Shared flash-stream helpers for MeshCore / Meshtastic nRF DFU paths."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import AsyncIterator, Callable, Optional

from src.api.firmware.esptool_stream import EspToolNdjsonStreamer
from src.api.firmware.nrf_dfu_streamer import AdafruitNrfDfuStreamer, RECOVERY_HINT
from src.api.firmware.uf2_volume_flasher import Uf2VolumeFlasher


class NrfFlashSession:
    """Run Adafruit serial DFU (or UF2 copy) and emit NDJSON for StreamingResponse."""

    def __init__(
        self,
        streamer: Optional[EspToolNdjsonStreamer] = None,
        dfu: Optional[AdafruitNrfDfuStreamer] = None,
        uf2: Optional[Uf2VolumeFlasher] = None,
    ) -> None:
        self._ndjson = (streamer or EspToolNdjsonStreamer()).ndjson
        self._dfu = dfu or AdafruitNrfDfuStreamer()
        self._uf2 = uf2 or Uf2VolumeFlasher()

    async def run(
        self,
        *,
        package: Path,
        port: str,
        mode: str = "dfu",
        release_source: Optional[Callable] = None,
        restore_source: Optional[Callable] = None,
        reconnect_sleep_s: float = 10.0,
        source_name: str = "USB source",
    ) -> AsyncIterator[bytes]:
        """``mode`` is ``dfu`` (zip) or ``uf2`` (volume copy)."""
        released = release_source is not None
        if released:
            yield self._ndjson({
                "type": "line",
                "stream": "stdout",
                "text": f"Releasing {port} ({source_name})…",
            })
            await release_source()

        success = False
        try:
            if mode == "uf2":
                async for chunk in self._run_uf2(package):
                    yield chunk
                    try:
                        event = json.loads(chunk)
                    except Exception:
                        continue
                    if event.get("type") == "result":
                        success = bool((event.get("result") or {}).get("success"))
            else:
                async for chunk in self._dfu.stream_dfu(package, port):
                    yield chunk
                    try:
                        event = json.loads(chunk)
                    except Exception:
                        continue
                    if event.get("type") == "result":
                        success = bool((event.get("result") or {}).get("success"))
        except Exception as exc:
            yield self._ndjson({
                "type": "line", "stream": "stderr", "text": str(exc),
            })
            if "UF2" in str(exc) or "bootloader" in str(exc).lower():
                yield self._ndjson({
                    "type": "line", "stream": "stderr", "text": RECOVERY_HINT,
                })
            yield self._ndjson({
                "type": "result",
                "result": {"returncode": -1, "success": False, "error": str(exc)},
            })
            success = False

        if released and restore_source is not None:
            if not success:
                yield self._ndjson({
                    "type": "line",
                    "stream": "stderr",
                    "text": (
                        "Flash failed. Board firmware was not updated. "
                        "Restoring USB capture…"
                    ),
                })
                await restore_source()
                yield self._ndjson({
                    "type": "line",
                    "stream": "stdout",
                    "text": f"{source_name} restored on {port}.",
                })
            else:
                yield self._ndjson({
                    "type": "line",
                    "stream": "stdout",
                    "text": "Waiting for the board to finish rebooting…",
                })
                await asyncio.sleep(reconnect_sleep_s)
                await restore_source()
                yield self._ndjson({
                    "type": "line",
                    "stream": "stdout",
                    "text": f"{source_name} reconnect attempted on {port}.",
                })

    async def _run_uf2(self, package: Path) -> AsyncIterator[bytes]:
        yield self._ndjson({
            "type": "line",
            "stream": "stdout",
            "text": "Looking for UF2 bootloader volume…",
        })
        loop = asyncio.get_running_loop()
        try:
            dest = await loop.run_in_executor(
                None, self._uf2.flash_uf2, package,
            )
        except Exception as exc:
            yield self._ndjson({
                "type": "line", "stream": "stderr", "text": str(exc),
            })
            yield self._ndjson({
                "type": "line", "stream": "stderr", "text": RECOVERY_HINT,
            })
            yield self._ndjson({
                "type": "result",
                "result": {"returncode": -1, "success": False, "error": str(exc)},
            })
            return
        yield self._ndjson({
            "type": "line",
            "stream": "stdout",
            "text": f"Copied UF2 to {dest}. Board should reboot on its own.",
        })
        yield self._ndjson({
            "type": "result",
            "result": {"returncode": 0, "success": True},
        })
