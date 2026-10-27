"""RTL-SDR P2000 (Dutch emergency dispatch) decoder: rtl_fm -> multimon-ng
-> decoded message log.

Unlike the FM listener (src/audio/rtl_listener.py), there's nothing here
meant to be listened to -- multimon-ng's own stdout IS the decoded
output. Read line by line and kept as an in-memory ring buffer, polled
by the frontend on the same status-polling convention the FM listener
already uses (no new WebSocket infrastructure).

Pipeline:  rtl_fm (demod to s16le PCM) | multimon-ng (decode to text)
No ffmpeg stage -- nothing here produces audio.

Fixed frequency/decoder, not user-tunable (unlike the FM listener's
frequency picker): P2000 (Netherlands emergency dispatch) runs FLEX on
169.65 MHz. Same shape as src/audio/pager_listener.py's PagerListener
(which still covers the generic Pagers/POCSAG kinds, both POCSAG-family,
still core) -- P2000 was split out because it's the one FLEX-only kind
and the one people actually want standalone.

Only one of RtlListener/PagerListener("pagers")/PagerListener("pocsag")/
P2000Listener may hold the RTL-SDR dongle at a time -- see
src/audio/sdr_registry.py. Manual-stop-required: starting one while
another is active raises RuntimeError rather than silently stopping the
other.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import shlex
import shutil
import signal
import time
from collections import deque
from typing import Optional

from src.audio import sdr_registry

logger = logging.getLogger(__name__)

_MAX_MESSAGES = 200
_IDLE_STOP_SECS = 600  # mirrors rtl_listener.py's convention
_DEVICE_SETTLE_SECS = 0.4
_START_CHECK_SECS = 0.4
_START_RETRIES = 3
_OWNER = "p2000"

_FREQUENCY_HZ = 169_650_000
_MULTIMON_ARGS = ["-a", "FLEX"]

_ERROR_RE = re.compile(
    r"failed|error|cannot|could not|invalid|no supported|usb_",
    re.IGNORECASE,
)

# multimon-ng prints one line per decoded page, prefixed by the decoder
# that caught it. Exact field layout can vary a little by multimon-ng
# version, so parsing is best-effort: unmatched-but-recognized lines are
# still surfaced with the raw text rather than silently dropped.
#
# Format confirmed against a real captured P2000 page (2026-07-13,
# `rtl_fm -f 169.65M -M fm -s 22050 -l 250 | multimon-ng -a FLEX -t raw
# /dev/stdin` run manually in a shell) -- it's pipe-delimited, NOT the
# colon/space format originally guessed from documentation alone:
#   FLEX|2026-07-13 18:51:53|1600/2/K/A|13.006|002029582 000120161 000120999|ALN|A1 13161 Heesterveld 1102 Amsterdam 67412
# Field 5 (capcode) can list several space-separated addresses for the same
# page (simulcast/alternate addressing) -- only the first is kept for the
# compact capcode column; the full line is always preserved in `raw`.
_FLEX_RE = re.compile(
    r"^FLEX\|(?P<ts>[^|]+)\|(?P<baud>[^/|]+)/(?P<level>\d)/(?P<phase>[^/|])/(?P<cycle>[^/|])\|"
    r"(?P<frame>[^|]+)\|(?P<capcode>[^|]+)\|(?P<kind>[^|]+)\|(?P<message>.*)$"
)


def _parse_line(text: str) -> Optional[dict]:
    """Best-effort structured extraction; always keeps the raw line too
    so nothing is lost if the format doesn't match what's expected."""
    now = time.time()
    m = _FLEX_RE.match(text)
    if m:
        return {
            "protocol": "FLEX",
            "capcode": m.group("capcode").split()[0],
            "message": m.group("message").strip(),
            "raw": text,
            "received_at": now,
        }
    if text.startswith(("FLEX|", "FLEX:")):
        # Recognized protocol prefix but didn't match the expected field
        # layout (version/format drift) -- still surface it raw rather
        # than silently dropping a real decoded page.
        return {
            "protocol": "unknown", "capcode": "", "message": text,
            "raw": text, "received_at": now,
        }
    return None  # startup banner, blank lines, etc -- not a decoded page


class P2000Listener:
    """Owns one rtl_fm|multimon-ng pipeline decoding P2000 (FLEX) pages."""

    def __init__(self) -> None:
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

    async def start(self) -> None:
        """Raises RuntimeError if binaries are missing or the dongle is
        currently claimed by another listener."""
        if shutil.which("rtl_fm") is None:
            raise RuntimeError("rtl_fm not found on PATH")
        if shutil.which("multimon-ng") is None:
            raise RuntimeError("multimon-ng not found on PATH")

        async with self._lock:
            if self.running:
                return  # already running, idempotent
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
            "kind": _OWNER,
            "running": self.running,
            "frequency_hz": _FREQUENCY_HZ,
            "frequency_mhz": round(_FREQUENCY_HZ / 1e6, 6),
            "message_count": len(self.messages),
            "messages": list(self.messages),
            "last_error": self._last_error,
            # Who currently holds the shared RTL-SDR dongle (None = free,
            # "p2000", or one of the other listeners' owner names).
            "dongle_owner": sdr_registry.current_owner(),
        }

    # ── pipeline management (call with self._lock held) ──────────

    async def _start_locked(self) -> None:
        rtl_cmd = [
            "rtl_fm", "-d", "0", "-f", str(_FREQUENCY_HZ),
            "-M", "fm", "-s", "22050", "-l", "250",
        ]
        multimon_cmd = ["multimon-ng", *_MULTIMON_ARGS, "-t", "raw", "/dev/stdin"]
        rtl_str = " ".join(shlex.quote(x) for x in rtl_cmd)
        mm_str = " ".join(shlex.quote(x) for x in multimon_cmd)
        cmd = f"{rtl_str} | {mm_str}"

        logger.info("P2000 listener starting: %s", cmd)
        self._last_error = ""
        self._proc = await asyncio.create_subprocess_exec(
            "/bin/bash", "-c", cmd,
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
        """Start the pipeline, retrying if rtl_fm can't open the dongle yet.

        Mirrors RtlListener/PagerListener's retry loop: on a fast
        start-right-after-stop the previous rtl_fm may still hold the USB
        device.
        """
        for attempt in range(1, _START_RETRIES + 1):
            await self._start_locked()
            await asyncio.sleep(_START_CHECK_SECS)
            if self._proc is not None and self._proc.returncode is None:
                return  # still alive -> device opened
            logger.warning(
                "P2000 listener start attempt %d/%d failed (%s); retrying",
                attempt, _START_RETRIES, self._last_error or "process exited",
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
            logger.info("P2000 listener stopped")

    # ── background tasks ──────────────────────────────────────────

    async def _read_loop(self, proc: asyncio.subprocess.Process) -> None:
        """Parse decoded pages from multimon-ng's stdout into the ring buffer."""
        try:
            while True:
                line = await proc.stdout.readline()
                if not line:
                    break
                text = line.decode(errors="replace").rstrip()
                if not text:
                    continue
                parsed = _parse_line(text)
                if parsed is not None:
                    self.messages.append(parsed)
        except asyncio.CancelledError:
            return
        # EOF: pipeline died on its own (dongle missing, rtl_fm crash, ...)
        if self._proc is proc:
            rc = proc.returncode
            self._last_error = self._last_error or f"pipeline exited (code {rc})"
            logger.warning("P2000 listener pipeline ended: %s", self._last_error)
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
                logger.debug("P2000 pipeline: %s", text)
                if _ERROR_RE.search(text):
                    self._last_error = text
        except asyncio.CancelledError:
            return

    async def _idle_watchdog(self) -> None:
        """Stop the pipeline when nobody has polled status for a while."""
        try:
            while True:
                await asyncio.sleep(30)
                idle = time.monotonic() - self._last_poll_at
                if idle >= _IDLE_STOP_SECS:
                    logger.info(
                        "P2000 listener idle for %.0f s -- stopping", idle,
                    )
                    async with self._lock:
                        await self._stop_locked()
                    return
        except asyncio.CancelledError:
            return
