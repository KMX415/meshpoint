"""RTL-SDR generic OOK/FSK decoder (rtl_433): weather stations, TPMS,
remote sensors, and hundreds of other 433/315/868 MHz devices.

Unlike the P2000/Pagers/POCSAG kinds (src/audio/pager_listener.py --
two piped processes, rtl_fm | multimon-ng), rtl_433 talks to the
RTL-SDR dongle directly: a single self-contained process, same as
RtlListener's rtl_fm but with its own built-in decoders for hundreds
of device protocols instead of one fixed demodulation mode.

Same shape as AcarsListener (plugins/apps/acars/backend/listener.py):
one self-contained process talking to the RTL-SDR dongle directly,
emitting one JSON object per decoded event on stdout.

`-F json` makes rtl_433 emit one JSON object per line per decoded
event on stdout (its own recommended machine-readable format --
tuner-detection/info logging stays on stderr) instead of the default
human-readable multi-line block format. The decoded field set varies
wildly by device model (a temperature sensor and a remote control
share almost no fields in common), so JSON keeps that flexible
without a fragile per-device regex -- the frontend just renders
whatever keys showed up on a given event.

Only one of RtlListener/PagerListener(*)/Rtl433Listener may hold the
RTL-SDR dongle at a time -- see src/audio/sdr_registry.py.
Manual-stop-required: starting one while another is active raises
RuntimeError rather than silently stopping the other.
"""

from __future__ import annotations

import asyncio
import json
import logging
import math
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
_IDLE_STOP_SECS = 600  # mirrors pager_listener.py's convention
_DEVICE_SETTLE_SECS = 0.4
_START_CHECK_SECS = 0.4
_START_RETRIES = 3
_OWNER = "rtl433"

# Always pass the administrator-selected frequency to rtl_433.

_ERROR_RE = re.compile(
    r"failed|error|cannot|could not|invalid|no supported|usb_",
    re.IGNORECASE,
)


class Rtl433Listener:
    """Owns one rtl_433 process decoding OOK/FSK devices as JSON events."""

    def __init__(self, frequency_mhz=None) -> None:
        self.frequency_hz = None if frequency_mhz is None else self.validate_frequency(frequency_mhz)
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

    @staticmethod
    def validate_frequency(value):
        if isinstance(value, bool):
            raise ValueError("Enter a receive frequency in MHz")
        number = float(value)
        if not math.isfinite(number) or not 24 <= number <= 1766:
            raise ValueError("Receive frequency must be between 24 and 1766 MHz")
        return round(number * 1e6)

    async def start(self, frequency_mhz=None) -> None:
        """Raises RuntimeError if rtl_433 is missing or the dongle is
        currently claimed by the FM listener or a pager kind."""
        if shutil.which("rtl_433") is None:
            raise RuntimeError("rtl_433 not found on PATH")

        async with self._lock:
            frequency = self.frequency_hz if frequency_mhz is None else self.validate_frequency(frequency_mhz)
            if frequency is None:
                raise ValueError("Choose the local receive frequency before starting")
            if self.running:
                if frequency != self.frequency_hz:
                    raise ValueError("Stop the receiver before changing frequency")
                return
            self.frequency_hz = frequency
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
            "frequency_mhz": self.frequency_hz / 1e6 if self.frequency_hz else None,
            "message_count": len(self.messages),
            "messages": list(self.messages),
            "last_error": self._last_error,
            # Who currently holds the shared RTL-SDR dongle (None = free,
            # "rtl433", or one of the other listeners' owner names).
            "dongle_owner": sdr_registry.current_owner(),
        }

    # ── pipeline management (call with self._lock held) ──────────

    async def _start_locked(self) -> None:
        # -F log alongside -F json: without it, rtl_433 suppresses its own
        # startup/device/error messages entirely ("Use "-F log" if you want
        # any messages, warnings, and errors in the console") -- meaning a
        # real fatal reason (device busy, PLL not locked, etc) would be
        # silently thrown away instead of reaching _stderr_loop below.
        cmd = ["rtl_433", "-f", str(self.frequency_hz), "-F", "json", "-F", "log"]
        logger.info("rtl_433 listener starting: %s", " ".join(cmd))
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
        """Start the process, retrying if rtl_433 can't open the dongle yet.

        Mirrors PagerListener/RtlListener's retry loop: on a fast
        start-right-after-stop the previous process may still hold the
        USB device.
        """
        for attempt in range(1, _START_RETRIES + 1):
            await self._start_locked()
            await asyncio.sleep(_START_CHECK_SECS)
            if self._proc is not None and self._proc.returncode is None:
                return  # still alive -> device opened
            logger.warning(
                "rtl_433 listener start attempt %d/%d failed (%s); retrying",
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
            logger.info("rtl_433 listener stopped")

    # ── background tasks ──────────────────────────────────────────

    async def _read_loop(self, proc: asyncio.subprocess.Process) -> None:
        """Parse one JSON event per line from rtl_433's stdout into the
        ring buffer. Non-JSON stray lines are ignored rather than
        crashing the reader."""
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
        # note the exit code -- an earlier benign stderr line (e.g. rtl_433's
        # own "-F log" hint, which contains "error" as a substring and so
        # gets picked up by _ERROR_RE) must not mask that the process
        # actually terminated.
        if self._proc is proc:
            rc = proc.returncode
            exit_note = f"process exited (code {rc})"
            self._last_error = f"{self._last_error} -- {exit_note}" if self._last_error else exit_note
            logger.warning("rtl_433 listener ended: %s", self._last_error)
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
                logger.debug("rtl_433: %s", text)
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
                        "rtl_433 listener idle for %.0f s -- stopping", idle,
                    )
                    async with self._lock:
                        await self._stop_locked()
                    return
        except asyncio.CancelledError:
            return
