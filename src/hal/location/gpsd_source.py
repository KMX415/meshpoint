"""gpsd location source: live fixes + satellite skyplot from a gpsd daemon.

Talks the gpsd JSON wire protocol directly over TCP (one JSON object
per newline, control commands like ``?WATCH={...};``). Rolling our own
~150 line client instead of pulling in ``python3-gps`` keeps the
dependency surface tight, gives clean asyncio semantics, and lets us
own the reconnect / backoff strategy.

Wire protocol crash course (from gpsd's ``gpsd_json(5)``):

    Client -> gpsd  : ``?WATCH={"enable":true,"json":true};\n``
    gpsd   -> client: ``{"class":"VERSION", ...}``
                      ``{"class":"DEVICES", ...}``
                      ``{"class":"WATCH", ...}``
                      ``{"class":"TPV", "mode":3, "lat":..., "lon":..., ...}``
                      ``{"class":"SKY", "satellites":[...], ...}``

TPV (Time-Position-Velocity) and SKY arrive once per receiver report
cycle (~1 Hz on most u-blox modules). DEVICES is published once at
connect plus on hotplug events.

We keep the latest of each class in memory and ``get_status()``
synthesizes a snapshot. The reader task is the only writer; the
public API is read-only and lock-free (Python's GIL guarantees
dict / dataclass assignment is atomic).
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Optional

from src.hal.location.base import LocationSource
from src.hal.location.models import (
    GpsDeviceInfo,
    GpsStatus,
    LocationFix,
    Satellite,
    SatellitesView,
    classify_gnss_id,
)

logger = logging.getLogger(__name__)

_WATCH_COMMAND = b'?WATCH={"enable":true,"json":true};\r\n'
_INITIAL_BACKOFF_SECONDS = 1.0
_MAX_BACKOFF_SECONDS = 30.0
_LINE_READ_BYTES_CAP = 64 * 1024  # gpsd lines are <2 KB; cap defends against runaway peer.


class GpsdSource(LocationSource):
    """Connect to a gpsd daemon and stream TPV + SKY + DEVICES reports.

    Reconnects with exponential backoff on connection drop, so plugging
    a USB GPS in or out at runtime self-heals without a service
    restart.
    """

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 2947,
        min_fix_quality: int = 1,
    ) -> None:
        self._host = host
        self._port = port
        self._min_fix_quality = min_fix_quality

        self._reader_task: Optional[asyncio.Task[None]] = None
        self._stop_event = asyncio.Event()

        self._latest_fix: Optional[LocationFix] = None
        self._latest_sats: Optional[SatellitesView] = None
        self._latest_device: Optional[GpsDeviceInfo] = None
        self._last_update: Optional[datetime] = None
        self._connected = False
        self._last_error: Optional[str] = None

    @property
    def source_name(self) -> str:
        return "gpsd"

    async def start(self) -> None:
        if self._reader_task is not None and not self._reader_task.done():
            return
        self._stop_event.clear()
        self._reader_task = asyncio.create_task(
            self._run_reader_loop(),
            name="gpsd-reader",
        )
        logger.info(
            "GPSd location source: connecting to %s:%d (min_fix_quality=%d)",
            self._host,
            self._port,
            self._min_fix_quality,
        )

    async def stop(self) -> None:
        self._stop_event.set()
        task = self._reader_task
        if task is None:
            return
        self._reader_task = None
        if task.done():
            return
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, Exception):
            pass

    def get_status(self) -> GpsStatus:
        if self._connected and self._latest_fix is not None:
            return GpsStatus(
                source="gpsd",
                available=True,
                fix=self._latest_fix,
                satellites=self._latest_sats,
                device=self._latest_device,
                last_update=self._last_update,
            )
        # Connection up but no fix yet -- still "available" so the
        # dashboard can show a "WAITING FOR FIX" state with a live
        # skyplot of any satellites we can already see.
        if self._connected:
            return GpsStatus(
                source="gpsd",
                available=True,
                fix=None,
                satellites=self._latest_sats,
                device=self._latest_device,
                last_update=self._last_update,
                error=None,
            )
        return GpsStatus(
            source="gpsd",
            available=False,
            fix=None,
            satellites=None,
            device=self._latest_device,
            last_update=self._last_update,
            error=self._last_error or "Not connected to gpsd",
        )

    async def _run_reader_loop(self) -> None:
        """Outer loop: connect, read, reconnect with exponential backoff."""
        backoff = _INITIAL_BACKOFF_SECONDS
        while not self._stop_event.is_set():
            try:
                await self._read_session()
                # Clean disconnect (gpsd shut down or sent EOF).
                backoff = _INITIAL_BACKOFF_SECONDS
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 -- defensive top-level
                self._last_error = f"{type(exc).__name__}: {exc}"
                logger.debug(
                    "gpsd session ended: %s -- reconnecting in %.1fs",
                    self._last_error,
                    backoff,
                )

            self._connected = False
            if self._stop_event.is_set():
                break

            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=backoff)
                break
            except asyncio.TimeoutError:
                pass
            backoff = min(backoff * 2, _MAX_BACKOFF_SECONDS)

    async def _read_session(self) -> None:
        """One connect -> WATCH -> readline loop -> drop iteration."""
        reader, writer = await asyncio.open_connection(self._host, self._port)
        try:
            writer.write(_WATCH_COMMAND)
            await writer.drain()
            self._connected = True
            self._last_error = None
            logger.info("gpsd connected at %s:%d", self._host, self._port)

            while not self._stop_event.is_set():
                line = await reader.readline()
                if not line:
                    # gpsd dropped the connection
                    return
                if len(line) > _LINE_READ_BYTES_CAP:
                    logger.warning(
                        "gpsd: dropped oversized message (%d bytes)", len(line)
                    )
                    continue
                self._handle_line(line)
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass

    def _handle_line(self, line: bytes) -> None:
        try:
            payload = json.loads(line.decode("utf-8", errors="replace"))
        except json.JSONDecodeError:
            logger.debug("gpsd: skipping non-JSON line: %r", line[:80])
            return

        kind = payload.get("class")
        if kind == "TPV":
            self._handle_tpv(payload)
        elif kind == "SKY":
            self._handle_sky(payload)
        elif kind == "DEVICES":
            self._handle_devices(payload)
        # VERSION, WATCH, ERROR etc. are noise for us.

        self._last_update = datetime.now(timezone.utc)

    def _handle_tpv(self, payload: dict) -> None:
        mode = int(payload.get("mode", 0))
        if mode < self._min_fix_quality:
            # Don't promote a no-fix or worse-than-required mode to
            # ``self._latest_fix``: that would jump the dashboard to
            # zero coordinates. Keep the previous good fix (if any).
            if self._latest_fix is None:
                self._latest_fix = LocationFix(
                    mode=mode,
                    latitude=None,
                    longitude=None,
                    altitude_m=None,
                )
            return

        self._latest_fix = LocationFix(
            mode=mode,
            latitude=_optional_float(payload, "lat"),
            longitude=_optional_float(payload, "lon"),
            altitude_m=_optional_float(payload, "altMSL", "alt"),
            speed_mps=_optional_float(payload, "speed"),
            track_deg=_optional_float(payload, "track"),
            time=_parse_iso_time(payload.get("time")),
            epx_m=_optional_float(payload, "epx"),
            epy_m=_optional_float(payload, "epy"),
            epv_m=_optional_float(payload, "epv"),
            hdop=_optional_float(payload, "hdop"),
            pdop=_optional_float(payload, "pdop"),
            vdop=_optional_float(payload, "vdop"),
        )

    def _handle_sky(self, payload: dict) -> None:
        raw_sats = payload.get("satellites") or []
        sats: list[Satellite] = []
        for entry in raw_sats:
            sats.append(
                Satellite(
                    prn=int(entry.get("PRN", 0)),
                    azimuth=_optional_float(entry, "az"),
                    elevation=_optional_float(entry, "el"),
                    snr_dbhz=_optional_float(entry, "ss"),
                    used=bool(entry.get("used", False)),
                    gnss=classify_gnss_id(entry.get("gnssid")),
                )
            )
        self._latest_sats = SatellitesView.from_satellites(sats)

        # SKY also carries DOP fields on some gpsd builds; merge into
        # the fix snapshot if present and we have a fix.
        if self._latest_fix is not None:
            updated_fields = {}
            for key in ("hdop", "pdop", "vdop"):
                value = _optional_float(payload, key)
                if value is not None:
                    updated_fields[key] = value
            if updated_fields:
                self._latest_fix = LocationFix(
                    mode=self._latest_fix.mode,
                    latitude=self._latest_fix.latitude,
                    longitude=self._latest_fix.longitude,
                    altitude_m=self._latest_fix.altitude_m,
                    speed_mps=self._latest_fix.speed_mps,
                    track_deg=self._latest_fix.track_deg,
                    time=self._latest_fix.time,
                    epx_m=self._latest_fix.epx_m,
                    epy_m=self._latest_fix.epy_m,
                    epv_m=self._latest_fix.epv_m,
                    hdop=updated_fields.get("hdop", self._latest_fix.hdop),
                    pdop=updated_fields.get("pdop", self._latest_fix.pdop),
                    vdop=updated_fields.get("vdop", self._latest_fix.vdop),
                )

    def _handle_devices(self, payload: dict) -> None:
        devices = payload.get("devices") or []
        if not devices:
            self._latest_device = None
            return
        first = devices[0]
        self._latest_device = GpsDeviceInfo(
            driver=str(first.get("driver", "unknown")),
            path=str(first.get("path", "")),
            model=_guess_device_model(first),
            subtype=first.get("subtype") or first.get("subtype1"),
        )


def _optional_float(payload: dict, *keys: str) -> Optional[float]:
    """Return the first numeric value for any of ``keys``, else ``None``."""
    for key in keys:
        value = payload.get(key)
        if value is None:
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return None


def _parse_iso_time(value) -> Optional[datetime]:
    if not isinstance(value, str):
        return None
    try:
        # gpsd emits ``"2026-05-30T16:37:01.000Z"``; Python 3.11+ handles
        # the trailing ``Z`` natively.
        normalized = value.replace("Z", "+00:00")
        return datetime.fromisoformat(normalized)
    except ValueError:
        return None


def _guess_device_model(device_payload: dict) -> Optional[str]:
    """Map gpsd's free-form device fields to a human-friendly model.

    Best-effort: gpsd populates ``driver`` ("u-blox"), and optionally
    ``subtype`` ("PROTVER 18.00"). We check for u-blox specifically
    because that's what every Meshpoint user's USB stick is going to
    be (u-blox 7 and u-blox 8 confirmed, others trivially extendable).
    """
    driver = (device_payload.get("driver") or "").lower()
    subtype = device_payload.get("subtype") or ""

    if "u-blox" in driver or "ublox" in driver:
        if "PROTVER 18" in subtype or "G80" in subtype.upper() or "M8" in subtype.upper():
            return "u-blox 8"
        if "PROTVER 14" in subtype or "G70" in subtype.upper():
            return "u-blox 7"
        return "u-blox"
    if not driver:
        return None
    return driver
