"""ADS-B (air traffic) listener: manages a dump1090 subprocess and polls its
built-in webserver for the current aircraft table.

Unlike RtlListener/PagerListener/Rtl433Listener -- which each parse a stream
of demodulated audio or discrete decoded events -- dump1090 is a complete,
self-contained 1090ES receiver with its own embedded HTTP server: `dump1090
--net --net-http-port <port>`. We spawn it once, then poll its own
`/data.json` every 2s for the full list of currently-tracked aircraft (a
live snapshot, not an append-only event log -- ADS-B naturally models as
"which aircraft are visible right now", the same way every other ADS-B web
UI, including dump1090's own bundled gmap.html, presents it).

Only one of RtlListener/PagerListener(*)/Rtl433Listener/DabListener/
AdsbListener may hold the RTL-SDR dongle at a time -- see
src/audio/sdr_registry.py. Manual-stop-required: starting one while another
is active raises RuntimeError rather than silently stopping the other.
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
import urllib.request
from typing import Optional

from src.audio import sdr_registry

logger = logging.getLogger(__name__)

_OWNER = "adsb"
_WEBSERVER_PORT = 8081
_POLL_SECS = 2.0
_IDLE_STOP_SECS = 600  # mirrors the other listeners' convention
_DEVICE_SETTLE_SECS = 0.4
_START_CHECK_SECS = 1.0
_START_RETRIES = 3

_ERROR_RE = re.compile(
    r"failed|error|cannot|could not|invalid|no supported|usb_",
    re.IGNORECASE,
)


class AdsbListener:
    """Owns one dump1090 process tracking ADS-B aircraft via its webserver API."""

    def __init__(self) -> None:
        self._proc: Optional[asyncio.subprocess.Process] = None
        self._stderr_task: Optional[asyncio.Task] = None
        self._poll_task: Optional[asyncio.Task] = None
        self._idle_task: Optional[asyncio.Task] = None
        self._lock = asyncio.Lock()
        self._last_error: str = ""
        self._last_poll_at: float = 0.0
        self._metric: bool = True
        self.aircraft: list[dict] = []

    @property
    def running(self) -> bool:
        return self._proc is not None and self._proc.returncode is None

    async def start(self, metric: bool = True) -> None:
        """Raises RuntimeError if dump1090 is missing or the dongle is
        currently claimed by another listener.

        `metric` selects dump1090's own `--metric` flag (meters/km/h
        instead of feet/knots in its output, including /data.json) --
        stashed on self so status() can tell the frontend which unit
        labels to render, and so a restart-while-running is a no-op that
        keeps the previously-started process's actual units.
        """
        if shutil.which("dump1090") is None:
            raise RuntimeError("dump1090 not found on PATH")

        async with self._lock:
            if self.running:
                return  # already running, idempotent
            self._metric = metric
            sdr_registry.claim(_OWNER)
            try:
                await self._start_locked_retrying()
            except Exception:
                sdr_registry.release(_OWNER)
                raise

    async def stop(self) -> None:
        async with self._lock:
            await self._stop_locked()
            self.aircraft = []

    def poll(self) -> dict:
        """Called by the status endpoint; marks activity for the idle watchdog."""
        self._last_poll_at = time.monotonic()
        return self.status()

    def status(self) -> dict:
        return {
            "running": self.running,
            "aircraft_count": len(self.aircraft),
            "aircraft": self.aircraft,
            "last_error": self._last_error,
            "metric": self._metric,
            # Who currently holds the shared RTL-SDR dongle (None = free,
            # "adsb" = this listener, or one of the sibling listeners' owner
            # names) -- lets the frontend show "busy" instead of "idle".
            "dongle_owner": sdr_registry.current_owner(),
        }

    # ── pipeline management (call with self._lock held) ──────────

    async def _start_locked(self) -> None:
        cmd = ["dump1090", "--net", "--net-http-port", str(_WEBSERVER_PORT)]
        if self._metric:
            cmd.append("--metric")
        logger.info("ADS-B listener starting: %s", " ".join(cmd))
        self._last_error = ""
        self._proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
            start_new_session=True,  # own process group -> killpg gets all
        )
        loop = asyncio.get_running_loop()
        self._stderr_task = loop.create_task(self._stderr_loop(self._proc))
        self._poll_task = loop.create_task(self._poll_loop())
        self._idle_task = loop.create_task(self._idle_watchdog())
        self._last_poll_at = time.monotonic()

    async def _start_locked_retrying(self) -> None:
        """Start dump1090, retrying if the dongle isn't released yet.

        Mirrors RtlListener/Rtl433Listener/PagerListener/DabListener's
        retry loop: on a fast restart the previous process may still hold
        the USB device.
        """
        for attempt in range(1, _START_RETRIES + 1):
            await self._start_locked()
            await asyncio.sleep(_START_CHECK_SECS)
            if self._proc is not None and self._proc.returncode is None:
                return  # still alive -> device opened
            logger.warning(
                "ADS-B listener start attempt %d/%d failed (%s); retrying",
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
        for attr in ("_stderr_task", "_poll_task", "_idle_task"):
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
            logger.info("ADS-B listener stopped")

    # ── background tasks ──────────────────────────────────────────

    def _fetch_aircraft_sync(self) -> Optional[list]:
        try:
            req = urllib.request.Request(
                f"http://127.0.0.1:{_WEBSERVER_PORT}/data.json", method="GET",
            )
            with urllib.request.urlopen(req, timeout=3) as resp:
                return json.loads(resp.read().decode())
        except Exception:
            return None

    async def _poll_loop(self) -> None:
        """Poll dump1090's own /data.json for the current aircraft table.

        Unlike DabListener's growing station list, this is a full snapshot
        each time -- an aircraft that's gone (out of range, transponder
        off) should disappear, so a successful poll wholesale-replaces
        self.aircraft rather than merging into it. A failed/empty poll
        leaves the previous table in place rather than blanking the tab
        for one transient hiccup.
        """
        try:
            while True:
                await asyncio.sleep(_POLL_SECS)
                raw = await asyncio.to_thread(self._fetch_aircraft_sync)
                if raw is None:
                    continue
                aircraft = []
                for a in raw:
                    entry = {
                        "hex": a.get("hex", ""),
                        "flight": (a.get("flight") or "").strip(),
                        "squawk": a.get("squawk", ""),
                        "altitude": a.get("altitude") if a.get("altitude") not in (None, "") else None,
                        "speed": a.get("speed"),
                        "track": a.get("track") if a.get("validtrack") else None,
                        "vert_rate": a.get("vert_rate"),
                        "lat": a.get("lat") if a.get("validposition") else None,
                        "lon": a.get("lon") if a.get("validposition") else None,
                        "messages": a.get("messages", 0),
                        "seen": a.get("seen", 0),
                    }
                    aircraft.append(entry)
                # Most recently heard first.
                aircraft.sort(key=lambda e: e["seen"])
                self.aircraft = aircraft
        except asyncio.CancelledError:
            return

    async def _stderr_loop(self, proc: asyncio.subprocess.Process) -> None:
        try:
            while True:
                line = await proc.stderr.readline()
                if not line:
                    return
                text = line.decode(errors="replace").rstrip()
                if not text:
                    continue
                logger.debug("dump1090: %s", text)
                if _ERROR_RE.search(text):
                    self._last_error = text
        except asyncio.CancelledError:
            return

    async def _idle_watchdog(self) -> None:
        """Stop dump1090 when nobody has polled status for a while."""
        try:
            while True:
                await asyncio.sleep(30)
                idle = time.monotonic() - self._last_poll_at
                if idle >= _IDLE_STOP_SECS:
                    logger.info(
                        "ADS-B listener idle for %.0f s -- stopping", idle,
                    )
                    async with self._lock:
                        await self._stop_locked()
                        self.aircraft = []
                    return
        except asyncio.CancelledError:
            return
