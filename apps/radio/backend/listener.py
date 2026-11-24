"""RTL-SDR audio listener: rtl_fm -> ffmpeg (MP3) -> fan-out to web clients.

Runs a demodulation pipeline on the RTL-SDR dongle (separate hardware from
the SX1302 concentrator) and fans the resulting MP3 byte stream out to any
number of subscribed HTTP clients. Audio only : no waterfall, no IQ.

Pipeline:  rtl_fm (demod to s16le PCM) | ffmpeg (encode MP3) -> chunks

Tuning is restart-based: rtl_fm has no runtime control channel, so every
tune() tears the pipeline down and spawns it fresh (~1 s gap). The two
processes are launched as one shell pipeline in their own process group so
stop() can kill both with a single signal.

The dongle must NEVER be hot-plugged: plug-in inrush browns out the M1's
internal USB hub (observed: CP2102/MeshCore drop, full Pi reboot). Leave it
permanently connected.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import shlex
import shutil
import signal
import time
from typing import Optional

from src.audio import sdr_registry

logger = logging.getLogger(__name__)

_SDR_OWNER = "radio"

# Per-mode rtl_fm arguments.
# Keep rtl_fm output rate (-r) explicitly aligned with ffmpeg input rate (-ar)
# for predictable audio pitch/speed and robust startup behavior.
_MODES = {
    "nfm": {"rtl_mode": "fm", "sample_args": ["-s", "16000", "-r", "16000"], "audio_rate": 16000},
    "am":  {"rtl_mode": "am", "sample_args": ["-s", "16000", "-r", "16000"], "audio_rate": 16000},
    "usb": {"rtl_mode": "usb", "sample_args": ["-s", "16000", "-r", "16000"], "audio_rate": 16000},
    "lsb": {"rtl_mode": "lsb", "sample_args": ["-s", "16000", "-r", "16000"], "audio_rate": 16000},
    "wfm": {
        "rtl_mode": "wbfm",
        "sample_args": ["-s", "200000", "-r", "32000"],
        "audio_rate": 32000,
    },
}

# R820T tuner range. Frequencies outside are rejected before touching rtl_fm.
MIN_FREQ_HZ = 24_000_000
MAX_FREQ_HZ = 1_766_000_000

_CHUNK_SIZE = 4096
_QUEUE_MAX_CHUNKS = 64          # ~256 KB ≈ 30 s at 64 kbps; slow clients drop oldest
_IDLE_STOP_SECS = 600           # free dongle + CPU when nobody streamed for 10 min
_MP3_BITRATE = "64k"

# Pre-encoder audio level (ffmpeg volume=). rtl_fm output runs hot and clips
# on strong signals; DEFAULT_VOLUME tames it. Tunable live from the panel;
# once the sweet spot is found, update DEFAULT_VOLUME to bake it in.
DEFAULT_VOLUME = 0.45
MIN_VOLUME = 0.05
MAX_VOLUME = 1.5

# Audio-level meter: parse ffmpeg ebur128 momentary loudness (LUFS) from
# stderr and map to a 0-100 bar. Post-demod audio level (activity), NOT a
# calibrated RF S-meter -- a single dongle held by rtl_fm can't give true RSSI.
_EBUR128_M_RE = re.compile(r"(?:^|\s)M:\s*(-?[\d.]+)")
_LUFS_FLOOR = -60.0   # -> 0 %
_LUFS_CEIL = -5.0     # -> 100 %
# Only these stderr lines count as real errors worth showing in status.
_ERROR_RE = re.compile(
    r"failed|error|cannot|could not|invalid|no supported|usb_",
    re.IGNORECASE,
)

# USB device release lag after killing the old rtl_fm, and startup retry
# tuning for the "Failed to open rtlsdr device #0" race on fast preset switches.
_DEVICE_SETTLE_SECS = 0.4
_START_CHECK_SECS = 0.4    # window to detect an immediate rtl_fm open failure
_START_RETRIES = 3         # total attempts before giving up

# RDS (WFM broadcast only). RDS rides the 57 kHz subcarrier of the FM MPX, so
# we demod wide (171 kHz) and tee the stream: redsea decodes RDS, ffmpeg
# lowpasses + de-emphasises the MPX back into listenable mono audio. One dongle,
# both jobs. redsea emits newline-delimited JSON to a file we tail.
_RDS_SAMPLE_RATE = 171000   # redsea's native MPX rate (no resample)
_RDS_OUTPUT_RATE = 32000    # mp3 audio rate out of the MPX path
_RDS_FILE = "/tmp/meshpoint_rds.jsonl"  # PrivateTmp: shared within the service


class RtlListener:
    """Owns the rtl_fm|ffmpeg pipeline and the subscriber fan-out."""

    def __init__(self, region="UNKNOWN", deemphasis_us=None) -> None:
        self.region = str(region).upper()
        self.deemphasis_us = deemphasis_us if deemphasis_us is not None else {"US": 75, "EU_868": 50}.get(self.region)
        if self.deemphasis_us not in (None, 50, 75):
            raise ValueError("FM audio correction must be 50 or 75 microseconds")
        self._proc: Optional[asyncio.subprocess.Process] = None
        self._reader_task: Optional[asyncio.Task] = None
        self._stderr_task: Optional[asyncio.Task] = None
        self._idle_task: Optional[asyncio.Task] = None
        self._rds_task: Optional[asyncio.Task] = None
        self._subscribers: set[asyncio.Queue[bytes]] = set()
        self._lock = asyncio.Lock()
        self._last_error: str = ""
        self._last_subscriber_at: float = 0.0
        self._has_redsea = shutil.which("redsea") is not None

        # Current tuning, reported via status()
        self.frequency_hz: int = 0
        self.mode: str = "nfm"
        # User-chosen preset label (e.g. "Radio 10"), if any -- purely
        # informational, stored so any consumer (sidebar mini-player,
        # a page reload) can show it without stations that lack RDS
        # falling back to a bare frequency. Empty for a manual
        # frequency-only tune.
        self.station_label: str = ""
        self.squelch: int = 0
        self.gain: Optional[float] = None  # None = tuner AGC
        # Pre-encoder audio level. rtl_fm runs hot; this tames it before the
        # MP3 encoder so strong signals don't clip ("overmodulated"). Tunable
        # live from the panel; DEFAULT_VOLUME is the bake-in default.
        self.volume: float = DEFAULT_VOLUME
        # Live audio-level meter (0-100), parsed from ebur128 loudness.
        self.audio_level: float = 0.0
        # RDS (WFM only): program service name, RadioText, program type,
        # and block error rate (-1 = unknown; 0 = perfect lock).
        self.rds_ps: str = ""
        self.rds_rt: str = ""
        self.rds_pty: str = ""
        self.rds_bler: float = -1.0

    # ── public API ────────────────────────────────────────────────

    @property
    def running(self) -> bool:
        return self._proc is not None and self._proc.returncode is None

    async def tune(
        self,
        frequency_hz: int,
        mode: str = "nfm",
        squelch: int = 0,
        gain: Optional[float] = None,
        volume: Optional[float] = None,
        station_label: str = "",
        deemphasis_us: Optional[int] = None,
    ) -> None:
        """(Re)start the pipeline with new parameters.

        Raises ValueError on bad input, RuntimeError if binaries are missing
        or the dongle is currently claimed by a pager listener (P2000/Pagers)
        -- stop that one first (see src/audio/sdr_registry.py).
        """
        emphasis = self.deemphasis_us if deemphasis_us is None else deemphasis_us
        if emphasis not in (None, 50, 75) or (mode == "wfm" and emphasis is None):
            raise ValueError("Choose 50 or 75 microseconds for FM audio correction")
        if mode not in _MODES:
            raise ValueError(f"unknown mode {mode!r}; one of {sorted(_MODES)}")
        if not MIN_FREQ_HZ <= frequency_hz <= MAX_FREQ_HZ:
            raise ValueError(
                f"frequency {frequency_hz} Hz outside tuner range "
                f"{MIN_FREQ_HZ}-{MAX_FREQ_HZ} Hz"
            )
        if shutil.which("rtl_fm") is None:
            raise RuntimeError("rtl_fm not found on PATH")
        if shutil.which("ffmpeg") is None:
            raise RuntimeError("ffmpeg not found on PATH")

        async with self._lock:
            was_running = self._proc is not None
            await self._stop_locked()
            sdr_registry.claim(_SDR_OWNER)
            self.frequency_hz = frequency_hz
            self.mode = mode
            self.deemphasis_us = emphasis
            self.squelch = max(0, int(squelch))
            self.gain = gain
            self.station_label = station_label
            if volume is not None:
                self.volume = min(max(float(volume), MIN_VOLUME), MAX_VOLUME)
            # When retuning, the old rtl_fm may not have released the USB
            # device yet (killpg reaps the shell before rtl_fm finishes
            # closing libusb) -> "Failed to open rtlsdr device #0". Let the
            # kernel free the dongle before the new rtl_fm grabs it.
            if was_running:
                await asyncio.sleep(_DEVICE_SETTLE_SECS)
            await self._start_locked_retrying()

    async def stop(self) -> None:
        async with self._lock:
            await self._stop_locked()
            # Only a genuine user-initiated stop clears the label -- NOT
            # _start_locked_retrying()'s internal mid-retry _stop_locked()
            # calls, which would otherwise wipe out the label tune() just
            # set before the pipeline even finished (re)starting.
            self.station_label = ""

    def subscribe(self) -> asyncio.Queue[bytes]:
        q: asyncio.Queue[bytes] = asyncio.Queue(maxsize=_QUEUE_MAX_CHUNKS)
        self._subscribers.add(q)
        self._last_subscriber_at = time.monotonic()
        return q

    def unsubscribe(self, q: asyncio.Queue[bytes]) -> None:
        self._subscribers.discard(q)
        self._last_subscriber_at = time.monotonic()

    def status(self) -> dict:
        return {
            "running": self.running,
            "frequency_hz": self.frequency_hz,
            "region": self.region,
            "deemphasis_us": self.deemphasis_us,
            "frequency_mhz": round(self.frequency_hz / 1e6, 6),
            "mode": self.mode,
            "station_label": self.station_label,
            "squelch": self.squelch,
            "gain": self.gain,
            "volume": self.volume,
            "audio_level": round(self.audio_level, 1),
            "rds_ps": self.rds_ps,
            "rds_rt": self.rds_rt,
            "rds_pty": self.rds_pty,
            "rds_bler": self.rds_bler,
            "listeners": len(self._subscribers),
            "last_error": self._last_error,
            # Who currently holds the shared RTL-SDR dongle (None = free,
            # "radio" = this listener, "p2000"/"pagers" = the other kind) --
            # lets the frontend show "busy" instead of a bare "idle" when a
            # sibling listener is the one actually holding the device.
            "dongle_owner": sdr_registry.current_owner(),
        }

    # ── pipeline management (call with self._lock held) ──────────

    async def _start_locked(self) -> None:
        self.rds_ps = ""
        self.rds_rt = ""
        self.rds_pty = ""
        self.rds_bler = -1.0
        want_rds = self.mode == "wfm" and self._has_redsea

        if want_rds:
            in_rate = _RDS_SAMPLE_RATE
            rtl_cmd = [
                "rtl_fm", "-d", "0",
                "-M", "fm", "-s", str(_RDS_SAMPLE_RATE), "-F", "9",
                "-f", str(self.frequency_hz),
            ]
            # MPX -> mono audio: strip pilot/stereo/RDS subcarriers (>15 kHz),
            # Apply the selected FM audio correction, then level/limiter/meter.
            af = (
                f"lowpass=f=15000,aemphasis=mode=reproduction:type={self.deemphasis_us}fm,"
                f"volume={self.volume:.3f},alimiter=limit=0.9:level=false,ebur128"
            )
            out_rate = _RDS_OUTPUT_RATE
        else:
            spec = _MODES[self.mode]
            in_rate = spec["audio_rate"]
            rtl_cmd = [
                "rtl_fm", "-d", "0",
                "-M", spec["rtl_mode"], *spec["sample_args"],
                "-f", str(self.frequency_hz),
            ]
            af = (
                (f"aemphasis=mode=reproduction:type={self.deemphasis_us}fm," if self.mode == "wfm" else "")
                + f"volume={self.volume:.3f},alimiter=limit=0.9:level=false,ebur128"
            )
            out_rate = in_rate

        if self.squelch > 0:
            rtl_cmd += ["-l", str(self.squelch)]
        if self.gain is not None:
            rtl_cmd += ["-g", str(self.gain)]
        rtl_cmd.append("-")

        ffmpeg_cmd = [
            # loglevel info so ebur128 prints momentary loudness to stderr
            # (parsed for the level meter); real errors are filtered separately.
            "ffmpeg", "-hide_banner", "-loglevel", "info",
            "-f", "s16le", "-ar", str(in_rate), "-ac", "1", "-i", "pipe:0",
            "-af", af,
            "-f", "mp3", "-codec:a", "libmp3lame", "-b:a", _MP3_BITRATE,
            "-ar", str(out_rate), "pipe:1",
        ]

        rtl_str = " ".join(shlex.quote(x) for x in rtl_cmd)
        ff_str = " ".join(shlex.quote(x) for x in ffmpeg_cmd)
        if want_rds:
            # tee rtl_fm's MPX to redsea (RDS -> JSON file) and ffmpeg (audio).
            # Needs bash for process substitution.
            # No -p (show-partial): only fully-received PS/RadioText, so the
            # display shows clean text instead of flickering half-decoded
            # fragments that would keep restarting the marquee. -E adds a
            # `bler` field (block error rate %) for the RDS quality meter.
            redsea = (
                f"redsea -r {_RDS_SAMPLE_RATE} -E "
                f"> {shlex.quote(_RDS_FILE)} 2>/dev/null"
            )
            cmd = f"{rtl_str} | tee >({redsea}) | {ff_str}"
        else:
            cmd = f"{rtl_str} | {ff_str}"

        logger.info("RTL listener starting%s: %s",
                    " (RDS)" if want_rds else "", cmd)
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
        if want_rds:
            self._rds_task = loop.create_task(self._rds_reader(_RDS_FILE))
        self._last_subscriber_at = time.monotonic()

    async def _start_locked_retrying(self) -> None:
        """Start the pipeline, retrying if rtl_fm can't open the dongle yet.

        On fast preset switches the previous rtl_fm may still hold the USB
        device; rtl_fm then exits immediately with "Failed to open rtlsdr
        device #0". Detect that (pipeline dies within _START_CHECK_SECS) and
        retry after letting the device settle.
        """
        for attempt in range(1, _START_RETRIES + 1):
            await self._start_locked()
            await asyncio.sleep(_START_CHECK_SECS)
            if self._proc is not None and self._proc.returncode is None:
                return  # still alive -> device opened
            # Pipeline collapsed (device busy / open failed). Clean up and retry.
            logger.warning(
                "RTL listener start attempt %d/%d failed (%s); retrying",
                attempt, _START_RETRIES, self._last_error or "process exited",
            )
            await self._stop_locked()
            if attempt < _START_RETRIES:
                await asyncio.sleep(_DEVICE_SETTLE_SECS)
        # Final attempt; leave it running (or with _last_error set) for status.
        await self._start_locked()

    async def _stop_locked(self) -> None:
        self.audio_level = 0.0
        self.rds_ps = ""
        self.rds_rt = ""
        self.rds_pty = ""
        self.rds_bler = -1.0
        proc, self._proc = self._proc, None
        for attr in ("_reader_task", "_stderr_task", "_idle_task", "_rds_task"):
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
            logger.info("RTL listener stopped")
        sdr_registry.release(_SDR_OWNER)

    # ── background tasks ──────────────────────────────────────────

    async def _read_loop(self, proc: asyncio.subprocess.Process) -> None:
        """Pump MP3 chunks from ffmpeg to every subscriber queue."""
        try:
            while True:
                chunk = await proc.stdout.read(_CHUNK_SIZE)
                if not chunk:
                    break
                for q in list(self._subscribers):
                    if q.full():
                        try:  # drop oldest so laggards hear live-ish audio
                            q.get_nowait()
                        except asyncio.QueueEmpty:
                            pass
                    q.put_nowait(chunk)
        except asyncio.CancelledError:
            return
        # EOF: pipeline died on its own (dongle missing, rtl_fm crash, ...)
        if self._proc is proc:
            rc = proc.returncode
            self._last_error = self._last_error or (
                f"pipeline exited (code {rc})"
            )
            logger.warning("RTL listener pipeline ended: %s", self._last_error)
            self._proc = None
            sdr_registry.release(_SDR_OWNER)
        for q in list(self._subscribers):
            q.put_nowait(b"")  # sentinel: stream over

    async def _stderr_loop(self, proc: asyncio.subprocess.Process) -> None:
        """Parse pipeline stderr for the level meter; keep real errors only.

        ebur128 (info level) floods stderr with momentary-loudness lines; we
        turn those into the 0-100 meter and must NOT treat them as errors.
        """
        try:
            while True:
                line = await proc.stderr.readline()
                if not line:
                    return
                text = line.decode(errors="replace").rstrip()
                if not text:
                    continue
                m = _EBUR128_M_RE.search(text)
                if m:
                    self._update_level(m.group(1))
                    continue
                logger.debug("rtl pipeline: %s", text)
                if _ERROR_RE.search(text):
                    self._last_error = text
        except asyncio.CancelledError:
            return

    def _update_level(self, lufs_str: str) -> None:
        try:
            lufs = float(lufs_str)
        except ValueError:
            return
        if lufs <= _LUFS_FLOOR:
            self.audio_level = 0.0
        elif lufs >= _LUFS_CEIL:
            self.audio_level = 100.0
        else:
            self.audio_level = (lufs - _LUFS_FLOOR) / (_LUFS_CEIL - _LUFS_FLOOR) * 100.0

    async def _rds_reader(self, path: str) -> None:
        """Tail redsea's newline-delimited JSON; keep the latest PS + RadioText.

        redsea (-p) emits objects with `ps`/`partial_ps` and
        `radiotext`/`partial_radiotext` as they decode. We follow the file
        from position 0 (the shell truncated it at start) and update the
        current station name / text.
        """
        pos = 0
        buf = ""
        try:
            while True:
                await asyncio.sleep(0.4)
                try:
                    with open(path, "r", encoding="utf-8", errors="replace") as f:
                        f.seek(pos)
                        chunk = f.read()
                        pos = f.tell()
                except FileNotFoundError:
                    continue
                if not chunk:
                    continue
                buf += chunk
                lines = buf.split("\n")
                buf = lines.pop()  # keep trailing partial line
                for line in lines:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                    except ValueError:
                        continue
                    # Only fully-received fields (no partial_*), to keep the
                    # display stable rather than flickering fragments.
                    ps = obj.get("ps")
                    if ps:
                        self.rds_ps = str(ps).strip()
                    rt = obj.get("radiotext")
                    if rt:
                        self.rds_rt = str(rt).strip()
                    pty = obj.get("prog_type") or obj.get("pty")
                    if pty:
                        self.rds_pty = str(pty).strip()
                    bler = obj.get("bler")
                    if bler is not None:
                        try:
                            self.rds_bler = float(bler)
                        except (TypeError, ValueError):
                            pass
        except asyncio.CancelledError:
            return
        except Exception:
            logger.exception("RDS reader error")

    async def _idle_watchdog(self) -> None:
        """Stop the pipeline when nobody has been streaming for a while."""
        try:
            while True:
                await asyncio.sleep(30)
                if self._subscribers:
                    continue
                idle = time.monotonic() - self._last_subscriber_at
                if idle >= _IDLE_STOP_SECS:
                    logger.info(
                        "RTL listener idle for %.0f s -- stopping", idle
                    )
                    async with self._lock:
                        await self._stop_locked()
                        self.station_label = ""
                    return
        except asyncio.CancelledError:
            return