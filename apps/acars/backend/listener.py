"""ACARS (aircraft VHF datalink) listener: manages an `acarsdec` subprocess
and parses its JSON output into a live message buffer.

Same shape as Rtl433Listener (src/audio/rtl433_listener.py): one
self-contained process talking to the RTL-SDR dongle directly, emitting
one JSON object per decoded message on stdout. acarsdec's
`--output json:file:path=-` is the machine-readable format (its startup /
tuner / error logging stays on stderr). Field set per message:
`timestamp`, `channel`, `freq`, `level`, `label`, `tail`, `flight`,
`text`, `msgno`, and -- when acarsdec was built with libacars and the
message is a recognised standard type -- a decoded `libacars` sub-object.

Only one of RtlListener/PagerListener(*)/Rtl433Listener/DabListener/
AdsbListener/AcarsListener may hold the RTL-SDR dongle at a time -- see
src/audio/sdr_registry.py. Manual-stop-required: starting one while
another is active raises RuntimeError rather than silently stopping the
other.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import shutil
import signal
import time
from collections import deque
from typing import Optional

from src.audio import sdr_registry

logger = logging.getLogger(__name__)

_MAX_MESSAGES = 200
_IDLE_STOP_SECS = 600  # mirrors rtl433_listener.py's convention
_DEVICE_SETTLE_SECS = 0.4
_START_CHECK_SECS = 0.4
_START_RETRIES = 3
_OWNER = "acars"

_DEFAULT_GAIN = "34"  # not AGC -- airband AGC overloads on strong ground stations
_DEFAULT_DEVICE = "0"

_ERROR_RE = re.compile(
    r"failed|error|cannot|could not|invalid|no supported|usb_|no data from",
    re.IGNORECASE,
)


def _normalize_frequencies(value) -> list:
    """Validate explicit VHF channels; never substitute a regional channel set."""
    if value is None:
        return []
    if not isinstance(value, list) or not 1 <= len(value) <= 8:
        raise ValueError("Choose one to eight ACARS frequencies in MHz")
    import math
    frequencies = [float(f) for f in value]
    if any(not math.isfinite(f) or not 118 <= f <= 137 for f in frequencies):
        raise ValueError("ACARS frequencies must be between 118 and 137 MHz")
    return [str(f).strip() for f in value]


class AcarsListener:
    """Owns one acarsdec process decoding ACARS messages as JSON events."""

    def __init__(self, frequencies=None, gain=None, device=None) -> None:
        self._frequencies = _normalize_frequencies(frequencies)
        self._gain = str(gain).strip() if gain not in (None, "") else _DEFAULT_GAIN
        self._device = str(device).strip() if device not in (None, "") else _DEFAULT_DEVICE
        self._proc: Optional[asyncio.subprocess.Process] = None
        self._reader_task: Optional[asyncio.Task] = None
        self._stderr_task: Optional[asyncio.Task] = None
        self._idle_task: Optional[asyncio.Task] = None
        self._lock = asyncio.Lock()
        self._last_error: str = ""
        self._last_poll_at: float = 0.0
        self.messages: "deque[dict]" = deque(maxlen=_MAX_MESSAGES)

    @property
    def running(self) -> bool:
        return self._proc is not None and self._proc.returncode is None

    async def start(self, frequencies=None) -> None:
        """Raises RuntimeError if acarsdec is missing or the dongle is
        currently claimed by another listener."""
        if shutil.which("acarsdec") is None:
            raise RuntimeError("acarsdec not found on PATH")

        async with self._lock:
            selected = self._frequencies if frequencies is None else _normalize_frequencies(frequencies)
            if not selected:
                raise ValueError("Choose local ACARS frequencies before starting")
            if self.running:
                if selected != self._frequencies:
                    raise ValueError("Stop ACARS before changing frequencies")
                return
            self._frequencies = selected
            sdr_registry.claim(_OWNER)
            try:
                await self._start_locked_retrying()
            except Exception:
                sdr_registry.release(_OWNER)
                raise

    async def stop(self) -> None:
        async with self._lock:
            await self._stop_locked()

    def clear(self) -> None:
        """Empty the on-screen message history. Independent of running/
        stopped state -- clearing does not touch the listener process."""
        self.messages.clear()

    def poll(self) -> dict:
        """Called by the status endpoint; marks activity for the idle watchdog."""
        self._last_poll_at = time.monotonic()
        return self.status()

    def status(self) -> dict:
        return {
            "running": self.running,
            "frequencies": self._frequencies,
            "message_count": len(self.messages),
            "messages": list(self.messages),
            "last_error": self._last_error,
            # Who currently holds the shared RTL-SDR dongle (None = free,
            # "acars", or one of the other listeners' owner names).
            "dongle_owner": sdr_registry.current_owner(),
        }

    # â”€â”€ pipeline management (call with self._lock held) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    async def _start_locked(self) -> None:
        cmd = [
            "acarsdec",
            "--output", "json:file:path=-",
            "-g", self._gain,
            "-e",  # drop empty / Q0 keep-alive frames
            "--rtlsdr", self._device,
            *self._frequencies,
        ]
        logger.info("ACARS listener starting: %s", " ".join(cmd))
        self._last_error = ""
        self._proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            start_new_session=True,  # own process group -> killpg gets all
        )
        loop = asyncio.get_running_loop()
        self._reader_task = loop.create_task(self._read_loop(self._proc))
        self._stderr_task = loop.create_task(self._stderr_loop(self._proc))
        self._idle_task = loop.create_task(self._idle_watchdog())
        self._last_poll_at = time.monotonic()

    async def _start_locked_retrying(self) -> None:
        """Start acarsdec, retrying if it can't open the dongle yet.

        Mirrors Rtl433Listener/RtlListener's retry loop: on a fast
        start-right-after-stop the previous process may still hold the USB
        device.
        """
        for attempt in range(1, _START_RETRIES + 1):
            await self._start_locked()
            await asyncio.sleep(_START_CHECK_SECS)
            if self._proc is not None and self._proc.returncode is None:
                return  # still alive -> device opened
            logger.warning(
                "ACARS listener start attempt %d/%d failed (%s); retrying",
                attempt, _START_RETRIES,
                self._last_error or "process exited",
            )
            await self._stop_locked_no_release()
            if attempt < _START_RETRIES:
                await asyncio.sleep(_DEVICE_SETTLE_SECS)
        # Final attempt; leave it running (or with _last_error set) for status.
        await self._start_locked()

    async def _stop_locked(self) -> None:
        await self._stop_locked_no_release()
        sdr_registry.release(_OWNER)

    async def _stop_locked_no_release(self) -> None:
        """Tear down the process without releasing the registry claim --
        used mid-retry, where we're about to start again and must not let
        another listener steal the dongle in between attempts."""
        proc, self._proc = self._proc, None
        for attr in ("_reader_task", "_stderr_task", "_idle_task"):
            task = getattr(self, attr)
            setattr(self, attr, None)
            if task is not None:
                task.cancel()
        if proc is not None and proc.returncode is None:
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            except (ProcessLookupError, PermissionError):
                pass
            try:
                await asyncio.wait_for(proc.wait(), timeout=3.0)
            except asyncio.TimeoutError:
                try:
                    os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                except (ProcessLookupError, PermissionError):
                    pass
                await proc.wait()
            logger.info("ACARS listener stopped")

    # â”€â”€ background tasks â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    async def _read_loop(self, proc: asyncio.subprocess.Process) -> None:
        """Parse one JSON message per line from acarsdec's stdout into the
        ring buffer. Non-JSON stray lines are ignored rather than crashing
        the reader."""
        try:
            while True:
                line = await proc.stdout.readline()
                if not line:
                    break
                text = line.decode(errors="replace").strip()
                if not text:
                    continue
                try:
                    event = json.loads(text)
                except ValueError:
                    continue
                if not isinstance(event, dict):
                    continue
                event["received_at"] = time.time()
                self.messages.append(event)
        except asyncio.CancelledError:
            return
        # EOF: process died on its own (dongle missing, crash, ...). Always
        # note the exit code even if an earlier benign stderr line already
        # set _last_error.
        if self._proc is proc:
            rc = proc.returncode
            exit_note = f"process exited (code {rc})"
            self._last_error = (
                f"{self._last_error} -- {exit_note}" if self._last_error else exit_note
            )
            logger.warning("ACARS listener ended: %s", self._last_error)
            self._proc = None
            sdr_registry.release(_OWNER)

    async def _stderr_loop(self, proc: asyncio.subprocess.Process) -> None:
        try:
            while True:
                line = await proc.stderr.readline()
                if not line:
                    return
                text = line.decode(errors="replace").rstrip()
                if not text:
                    continue
                logger.debug("acarsdec: %s", text)
                if _ERROR_RE.search(text):
                    self._last_error = text
        except asyncio.CancelledError:
            return

    async def _idle_watchdog(self) -> None:
        """Stop the process when nobody has polled status for a while."""
        try:
            while True:
                await asyncio.sleep(30)
                idle = time.monotonic() - self._last_poll_at
                if idle >= _IDLE_STOP_SECS:
                    logger.info(
                        "ACARS listener idle for %.0f s -- stopping", idle,
                    )
                    async with self._lock:
                        await self._stop_locked()
                    return
        except asyncio.CancelledError:
            return
