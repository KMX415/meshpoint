"""DAB/DAB+ listener: manages a welle-cli subprocess (webserver mode) and
proxies its ensemble/station status and MP3 streams to the dashboard.

Unlike RtlListener/PagerListener/Rtl433Listener -- which each own a demod
pipeline we build ourselves -- welle-cli is a complete, self-contained
DAB+ receiver with its own embedded HTTP server:
`welle-cli -c <channel> -w <port>`. We spawn it once per tune(), poll its
`/mux.json` for the ensemble label and decoded station list (service id,
name, DLS "now playing" text, SNR), and proxy individual `/mp3/<sid>`
audio streams on demand. welle-cli decodes each requested service on
demand and can serve several simultaneous HTTP clients itself, so the
stream proxy is a thin per-request pass-through (curl | chunks), not a
shared fan-out like RtlListener's single rtl_fm pipeline.

Only one of RtlListener/PagerListener(*)/Rtl433Listener/DabListener may
hold the RTL-SDR dongle at a time -- see src/audio/sdr_registry.py.
Manual-stop-required: starting one while another is active raises
RuntimeError rather than silently stopping the other.
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
from typing import AsyncIterator, Optional

from src.audio import sdr_registry

logger = logging.getLogger(__name__)

_OWNER = "dab"
_WEBSERVER_PORT = 7979
_MUX_POLL_SECS = 2.0
_IDLE_STOP_SECS = 600  # mirrors the other listeners' convention
_DEVICE_SETTLE_SECS = 0.4
_START_CHECK_SECS = 1.5  # welle-cli takes longer to fail-fast than rtl_fm
_START_RETRIES = 3
_STREAM_CHUNK_SIZE = 4096

_CHANNEL_RE = re.compile(r"^[0-9A-Z]{1,4}$")
_ERROR_RE = re.compile(
    r"failed|error|cannot|could not|invalid|no supported|usb_",
    re.IGNORECASE,
)
# welle-cli's OFDM sync loop logs routine retry chatter ("Lost coarse
# sync", "SyncOnPhase failed") on the way to a normal, successful lock --
# not a real error, even though it matches _ERROR_RE's "failed"/"lost".
_BENIGN_PREFIX_RE = re.compile(r"^ofdm-processor:", re.IGNORECASE)


class DabListener:
    """Owns one welle-cli process decoding a DAB+ ensemble via its webserver API."""

    def __init__(self) -> None:
        self._proc: Optional[asyncio.subprocess.Process] = None
        self._stderr_task: Optional[asyncio.Task] = None
        self._poll_task: Optional[asyncio.Task] = None
        self._idle_task: Optional[asyncio.Task] = None
        self._lock = asyncio.Lock()
        self._last_error: str = ""
        self._last_poll_at: float = 0.0

        self.channel: str = ""
        self.ensemble_label: str = ""
        self.snr: float = 0.0
        # Audio-capable services only (data-only services like TPEG have no
        # url_mp3 in welle-cli's mux.json and can't be streamed).
        self.services: list[dict] = []

    # ── public API ────────────────────────────────────────────────

    @property
    def running(self) -> bool:
        return self._proc is not None and self._proc.returncode is None

    async def tune(self, channel: str) -> None:
        """(Re)start welle-cli tuned to *channel* (e.g. "12C").

        Raises ValueError on bad input, RuntimeError if welle-cli is
        missing or the dongle is currently claimed by another listener.
        """
        channel = channel.strip().upper()
        if not _CHANNEL_RE.match(channel):
            raise ValueError(f"invalid DAB channel {channel!r}")
        if shutil.which("welle-cli") is None:
            raise RuntimeError("welle-cli not found on PATH")

        async with self._lock:
            was_running = self._proc is not None
            await self._stop_locked_no_release()
            sdr_registry.claim(_OWNER)
            try:
                self.channel = channel
                self.ensemble_label = ""
                self.snr = 0.0
                self.services = []
                if was_running:
                    await asyncio.sleep(_DEVICE_SETTLE_SECS)
                await self._start_locked_retrying()
            except Exception:
                sdr_registry.release(_OWNER)
                raise

    async def stop(self) -> None:
        async with self._lock:
            await self._stop_locked()
            self.channel = ""
            self.ensemble_label = ""
            self.snr = 0.0
            self.services = []
            self._last_error = ""

    def status(self) -> dict:
        return {
            "running": self.running,
            "channel": self.channel,
            "ensemble_label": self.ensemble_label,
            "snr": round(self.snr, 1),
            "services": self.services,
            "last_error": self._last_error,
            # Who currently holds the shared RTL-SDR dongle (None = free,
            # "dab" = this listener, or one of the sibling listeners' owner
            # names) -- lets the frontend show "busy" instead of "idle".
            "dongle_owner": sdr_registry.current_owner(),
        }

    def poll(self) -> dict:
        """Called by the status endpoint; marks activity for the idle watchdog."""
        self._last_poll_at = time.monotonic()
        return self.status()

    async def stream(self, sid: str) -> AsyncIterator[bytes]:
        """Proxy welle-cli's own `/mp3/<sid>` stream for one client.

        welle-cli's webserver decodes each requested service on demand and
        can serve several simultaneous HTTP clients itself, so this is a
        thin per-request pass-through rather than a shared fan-out --
        unlike RtlListener there is no single demod pipeline to multiplex.
        *sid* is used exactly as welle-cli's own mux.json reports it (e.g.
        "0x8201"), so no extra encoding is needed here.
        """
        if not self.running:
            raise RuntimeError("DAB listener not running -- tune first")
        url = f"http://127.0.0.1:{_WEBSERVER_PORT}/mp3/{sid}"
        proc = await asyncio.create_subprocess_exec(
            "curl", "-sN", url,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        try:
            while True:
                chunk = await proc.stdout.read(_STREAM_CHUNK_SIZE)
                if not chunk:
                    break
                yield chunk
        finally:
            if proc.returncode is None:
                proc.kill()
                await proc.wait()

    # ── pipeline management (call with self._lock held) ──────────

    async def _start_locked(self) -> None:
        cmd = ["welle-cli", "-c", self.channel, "-w", str(_WEBSERVER_PORT)]
        logger.info("DAB listener starting: %s", " ".join(cmd))
        self._last_error = ""
        self._proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
            start_new_session=True,  # own process group -> killpg gets all
        )
        loop = asyncio.get_running_loop()
        self._stderr_task = loop.create_task(self._stderr_loop(self._proc))
        self._poll_task = loop.create_task(self._mux_poll_loop())
        self._idle_task = loop.create_task(self._idle_watchdog())
        self._last_poll_at = time.monotonic()

    async def _start_locked_retrying(self) -> None:
        """Start welle-cli, retrying if the dongle isn't released yet.

        Mirrors RtlListener/Rtl433Listener/PagerListener's retry loop: on a
        fast retune the previous process may still hold the USB device.
        """
        for attempt in range(1, _START_RETRIES + 1):
            await self._start_locked()
            await asyncio.sleep(_START_CHECK_SECS)
            if self._proc is not None and self._proc.returncode is None:
                return  # still alive -> device opened
            logger.warning(
                "DAB listener start attempt %d/%d failed (%s); retrying",
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
            logger.info("DAB listener stopped")

    # ── background tasks ──────────────────────────────────────────

    async def _stderr_loop(self, proc: asyncio.subprocess.Process) -> None:
        try:
            while True:
                line = await proc.stderr.readline()
                if not line:
                    return
                text = line.decode(errors="replace").rstrip()
                if not text:
                    continue
                logger.debug("welle-cli: %s", text)
                if _BENIGN_PREFIX_RE.match(text):
                    continue
                if _ERROR_RE.search(text):
                    self._last_error = text
        except asyncio.CancelledError:
            return

    def _fetch_mux_json_sync(self) -> Optional[dict]:
        try:
            req = urllib.request.Request(
                f"http://127.0.0.1:{_WEBSERVER_PORT}/mux.json", method="GET",
            )
            with urllib.request.urlopen(req, timeout=3) as resp:
                return json.loads(resp.read().decode())
        except Exception:
            return None

    async def _mux_poll_loop(self) -> None:
        """Poll welle-cli's own /mux.json for ensemble label, SNR, and the
        decoded station list. Runs for as long as welle-cli is up --
        stations appear incrementally as welle-cli decodes each one, so
        services only grows, never gets wiped by a transient empty poll.
        """
        try:
            while True:
                await asyncio.sleep(_MUX_POLL_SECS)
                data = await asyncio.to_thread(self._fetch_mux_json_sync)
                if not data:
                    continue
                label = (
                    data.get("ensemble", {}).get("label", {}).get("label", "")
                )
                if label:
                    self.ensemble_label = label.strip()
                demod = data.get("demodulator", {})
                snr = demod.get("snr")
                if isinstance(snr, (int, float)):
                    self.snr = float(snr)
                services = []
                for s in data.get("services", []):
                    sid = s.get("sid")
                    label = (s.get("label") or {}).get("label", "").strip()
                    # Data-only services (e.g. TPEG) have no url_mp3 and
                    # can't be streamed -- skip them from the station list.
                    if not sid or not label or not s.get("url_mp3"):
                        continue
                    services.append({
                        "sid": sid,
                        "label": label,
                        "dls": (s.get("dls") or {}).get("label", "").strip(),
                        "pty": s.get("ptystring", ""),
                    })
                if services:
                    self.services = services
        except asyncio.CancelledError:
            return

    async def _idle_watchdog(self) -> None:
        """Stop welle-cli when nobody has polled status for a while."""
        try:
            while True:
                await asyncio.sleep(30)
                idle = time.monotonic() - self._last_poll_at
                if idle >= _IDLE_STOP_SECS:
                    logger.info(
                        "DAB listener idle for %.0f s -- stopping", idle,
                    )
                    async with self._lock:
                        await self._stop_locked()
                        self.channel = ""
                        self.ensemble_label = ""
                        self.snr = 0.0
                        self.services = []
                        self._last_error = ""
                    return
        except asyncio.CancelledError:
            return
