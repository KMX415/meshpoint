"""Capture source for MeshCore USB nodes.

Connects to a MeshCore companion radio via USB serial using the
``meshcore`` Python library, subscribes to incoming events, and
yields them as RawCapture objects for the pipeline.

Includes auto-reconnect with exponential backoff and a periodic
health check so the source self-heals after serial disconnects.

Events are JSON-serialised and decoded downstream by
``meshcore_event_adapter.adapt_event``.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import AsyncIterator, Optional

from src.capture.base import CaptureSource
from src.models.packet import Protocol, RawCapture
from src.models.signal import SignalMetrics

logger = logging.getLogger(__name__)

_EMPTY_SIGNAL = SignalMetrics(
    rssi=-120.0, snr=0.0, frequency_mhz=0.0,
    spreading_factor=0, bandwidth_khz=0.0, coding_rate="N/A",
)

_HEALTH_CHECK_INTERVAL_SECONDS = 180
_HEALTH_CHECK_RETRY_DELAY_SECONDS = 20
_HEALTH_CHECK_MAX_FAILURES = 2
_RECENT_EVENT_HEALTHY_WINDOW_SECONDS = 120
_MESHCORE_COMMAND_TIMEOUT_SECONDS = 12.0
_HEALTH_CHECK_TIMEOUT_SECONDS = 15.0
_RECONNECT_BASE_DELAY_SECONDS = 5
_RECONNECT_MAX_DELAY_SECONDS = 60
_DTR_RESET_PULSE_SECONDS = 0.1


class MeshcoreUsbCaptureSource(CaptureSource):
    """Receives packets from a MeshCore device connected via USB serial."""

    def __init__(
        self,
        serial_port: Optional[str] = None,
        baud_rate: int = 115200,
        auto_detect: bool = True,
    ):
        self._configured_port = serial_port
        self._baud_rate = baud_rate
        self._auto_detect = auto_detect
        self._meshcore = None
        self._queue: asyncio.Queue = asyncio.Queue(maxsize=500)
        self._running = False
        self._connected = False
        self._subscriptions: list = []
        self._resolved_port: Optional[str] = None
        self._health_task: Optional[asyncio.Task] = None
        self._reconnect_task: Optional[asyncio.Task] = None
        self._last_rf_signal: Optional[SignalMetrics] = None
        self._last_event_at: float = 0.0
        self._on_connected_callback = None

    @property
    def name(self) -> str:
        return "meshcore_usb"

    @property
    def is_running(self) -> bool:
        return self._running

    async def start(self) -> None:
        port = await self._resolve_port()
        if port is None:
            # Expected when meshcore_usb is enabled in config but no
            # companion is currently plugged in. Not an error condition,
            # just a state. Plug in a device and restart the service to
            # activate this source.
            logger.info(
                "No MeshCore USB device detected -- source idle "
                "(plug in a companion and restart to activate)"
            )
            return

        self._resolved_port = port
        self._running = True
        await self._connect(port)

        if self._connected:
            self._health_task = asyncio.create_task(
                self._health_check_loop(), name="meshcore-health"
            )
            return

        # Initial handshake failed. The device may still be coming up
        # (ESP32-S3 needs ~6-10s to be USB-ready after a reboot, longer
        # than the meshcore library's 5s handshake timeout). Schedule a
        # background reconnect with exponential backoff so the source
        # recovers on its own without blocking service startup.
        logger.info(
            "MeshCore USB initial connect failed -- scheduling background "
            "reconnect"
        )
        self._reconnect_task = asyncio.create_task(
            self._reconnect_until_connected(),
            name="meshcore-initial-reconnect",
        )

    async def stop(self) -> None:
        self._running = False
        if self._reconnect_task:
            self._reconnect_task.cancel()
            try:
                await self._reconnect_task
            except asyncio.CancelledError:
                pass
            self._reconnect_task = None
        if self._health_task:
            self._health_task.cancel()
            try:
                await self._health_task
            except asyncio.CancelledError:
                pass
            self._health_task = None
        await self._disconnect()
        logger.info("MeshCore USB source stopped")

    async def _reconnect_until_connected(self) -> None:
        """Background reconnect after a failed initial handshake.

        Promotes itself to the standard health-check loop once connected
        so subsequent disconnects are handled normally.
        """
        try:
            await self._reconnect()
            if self._connected:
                self._health_task = asyncio.create_task(
                    self._health_check_loop(), name="meshcore-health"
                )
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.exception("MeshCore USB initial reconnect loop error")

    async def packets(self) -> AsyncIterator[RawCapture]:
        if not self._running:
            return
        while self._running:
            try:
                event = await asyncio.wait_for(
                    self._queue.get(), timeout=1.0
                )
                raw = self._wrap_event(event)
                if raw is not None:
                    yield raw
            except asyncio.TimeoutError:
                continue

    async def _connect(self, port: str) -> None:
        try:
            from meshcore import MeshCore, EventType

            self._meshcore = await MeshCore.create_serial(
                port,
                self._baud_rate,
                default_timeout=_MESHCORE_COMMAND_TIMEOUT_SECONDS,
            )
            if self._meshcore is None:
                logger.error(
                    "MeshCore companion handshake failed on %s. "
                    "Verify the device is running Companion USB firmware "
                    "and that no other process is holding the port.",
                    port,
                )
                self._connected = False
                return

            self._connected = True

            for event_type in (
                EventType.RX_LOG_DATA,
                EventType.RAW_DATA,
                EventType.CONTACT_MSG_RECV,
                EventType.CHANNEL_MSG_RECV,
                EventType.ADVERTISEMENT,
                EventType.DISCONNECTED,
            ):
                sub = self._meshcore.subscribe(event_type, self._on_event)
                self._subscriptions.append(sub)

            await self._meshcore.start_auto_message_fetching()
            logger.info(
                "MeshCore USB source started on %s @ %d baud",
                port, self._baud_rate,
            )
            if self._on_connected_callback:
                asyncio.create_task(
                    self._on_connected_callback(),
                    name="meshcore-on-connected",
                )
        except Exception:
            logger.exception(
                "Failed to start MeshCore USB source on %s", port
            )
            self._connected = False

    async def _disconnect(self) -> None:
        self._connected = False
        if self._meshcore:
            for sub in self._subscriptions:
                self._meshcore.unsubscribe(sub)
            self._subscriptions.clear()
            try:
                await self._meshcore.stop_auto_message_fetching()
            except Exception:
                pass
            try:
                await self._meshcore.disconnect()
            except Exception:
                pass
            self._meshcore = None

    async def _reconnect(self) -> None:
        """Disconnect, wait with backoff, and reconnect.

        On retries (not the first attempt) we pulse DTR low briefly
        before opening the port. On most ESP32 dev boards (Heltec V3
        included) DTR is wired to the chip's RESET pin, so a short
        pulse triggers a hardware reset of the companion. This
        recovers from a stuck USB-CDC state that otherwise requires
        a manual unplug/replug. On boards where DTR is not wired
        to RESET the pulse is a harmless no-op.
        """
        await self._disconnect()
        delay = _RECONNECT_BASE_DELAY_SECONDS
        attempt = 0

        while self._running:
            logger.info(
                "MeshCore USB reconnecting in %ds...", delay
            )
            await asyncio.sleep(delay)
            if not self._running:
                return

            attempt += 1
            if attempt >= 2 and self._resolved_port:
                await asyncio.to_thread(
                    self._pulse_dtr_reset, self._resolved_port
                )
                # Give the chip a moment to come back from reset.
                await asyncio.sleep(2.0)

            await self._connect(self._resolved_port)
            if self._connected:
                logger.info("MeshCore USB reconnected successfully")
                return

            delay = min(delay * 2, _RECONNECT_MAX_DELAY_SECONDS)

    def _pulse_dtr_reset(self, port: str) -> None:
        """Toggle DTR low to soft-reset an ESP32 companion. Best-effort.

        Runs in a worker thread (called via asyncio.to_thread) because
        pyserial's open and the DTR sleep are blocking. Safe to fail
        silently: if the host's serial driver doesn't expose DTR or the
        port is unavailable, we just skip and let the regular reconnect
        attempt proceed.
        """
        try:
            import serial  # transitive dep via meshcore lib
        except ImportError:
            return
        try:
            import time as _time
            with serial.Serial(port, self._baud_rate, timeout=0.5) as ser:
                ser.dtr = False
                _time.sleep(_DTR_RESET_PULSE_SECONDS)
                ser.dtr = True
            logger.info(
                "MeshCore USB pulsed DTR on %s to attempt soft reset",
                port,
            )
        except Exception as exc:
            logger.debug(
                "MeshCore USB DTR pulse skipped on %s: %s", port, exc
            )

    async def _health_check_loop(self) -> None:
        """Periodically verify the serial companion is still responding.

        Two defenses against false positives that used to trigger
        spurious reconnects (which themselves cost ~15-20s of RX
        downtime because they DTR-reboot the companion):

        1. Skip the active probe entirely if any event arrived from
           the device within the last RECENT_EVENT_HEALTHY_WINDOW
           seconds. Inbound events ARE proof of life: no point asking.
        2. Tolerate transient probe failures. A single missed response
           can happen when the device is busy processing an inbound
           RF frame or fetching queued messages. We retry once after
           a short delay and only reconnect if the second probe also
           fails.
        """
        consecutive_failures = 0
        try:
            while self._running and self._connected:
                await asyncio.sleep(_HEALTH_CHECK_INTERVAL_SECONDS)
                if not self._running:
                    return

                if self._has_recent_event_activity():
                    consecutive_failures = 0
                    continue

                if await self._check_health():
                    consecutive_failures = 0
                    continue

                consecutive_failures += 1
                logger.info(
                    "MeshCore USB health probe missed (%d/%d)",
                    consecutive_failures, _HEALTH_CHECK_MAX_FAILURES,
                )

                if consecutive_failures < _HEALTH_CHECK_MAX_FAILURES:
                    await asyncio.sleep(_HEALTH_CHECK_RETRY_DELAY_SECONDS)
                    continue

                logger.warning(
                    "MeshCore USB health check failed %d times -- "
                    "reconnecting",
                    _HEALTH_CHECK_MAX_FAILURES,
                )
                consecutive_failures = 0
                await self._reconnect()
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.exception("MeshCore USB health check loop error")

    def _has_recent_event_activity(self) -> bool:
        if self._last_event_at == 0.0:
            return False
        now = asyncio.get_event_loop().time()
        return (now - self._last_event_at) < _RECENT_EVENT_HEALTHY_WINDOW_SECONDS

    async def _check_health(self) -> bool:
        """Send a device query and verify we get a response."""
        if not self._meshcore:
            return False
        try:
            from meshcore import EventType

            result = await asyncio.wait_for(
                self._meshcore.commands.send_device_query(),
                timeout=_HEALTH_CHECK_TIMEOUT_SECONDS,
            )
            return result.type != EventType.ERROR
        except Exception:
            return False

    async def _on_event(self, event) -> None:
        if not self._running:
            return
        # Any event from the device is proof the connection is alive.
        # The health check loop uses this to skip its active probe.
        self._last_event_at = asyncio.get_event_loop().time()
        try:
            self._queue.put_nowait(event)
        except asyncio.QueueFull:
            logger.warning("MeshCore USB queue full, dropping event")

    def _wrap_event(self, event) -> Optional[RawCapture]:
        """Serialise a meshcore Event into a RawCapture envelope."""
        payload_dict = (
            event.payload if isinstance(event.payload, dict) else {}
        )
        etype = (
            event.type.value
            if hasattr(event.type, "value")
            else str(event.type)
        )

        signal = _extract_signal(payload_dict)

        if etype == "rx_log_data":
            if signal.rssi > -119.0:
                self._last_rf_signal = signal
            return None

        safe_payload = _make_json_safe(payload_dict)

        if etype in ("channel_message", "contact_message"):
            if self._last_rf_signal and signal.rssi <= -119.0:
                safe_payload["RSSI"] = self._last_rf_signal.rssi
                signal = self._last_rf_signal
            self._last_rf_signal = None

        envelope = {
            "event_type": etype,
            "payload": safe_payload,
        }
        return RawCapture(
            payload=json.dumps(envelope).encode("utf-8"),
            signal=signal,
            capture_source="meshcore_usb",
            protocol_hint=Protocol.MESHCORE,
        )

    def set_connected_callback(self, callback) -> None:
        """Register a coroutine called after every successful connection."""
        self._on_connected_callback = callback

    async def restart_auto_fetching(self) -> None:
        """Re-enable auto message fetching after TX operations."""
        if self._meshcore and self._connected:
            try:
                await self._meshcore.start_auto_message_fetching()
                logger.info("MeshCore auto message fetching restarted")
            except Exception:
                logger.debug("Failed to restart auto fetching", exc_info=True)

    async def _resolve_port(self) -> Optional[str]:
        if self._configured_port:
            return self._configured_port
        if not self._auto_detect:
            return None
        from src.capture.meshcore_usb_detect import detect_meshcore_port
        return await detect_meshcore_port(baud=self._baud_rate)


def _extract_signal(payload: dict) -> SignalMetrics:
    rssi = payload.get("rssi", payload.get("RSSI"))
    snr = payload.get("snr", payload.get("SNR"))
    if rssi is None and snr is None:
        return _EMPTY_SIGNAL
    return SignalMetrics(
        rssi=float(rssi) if rssi is not None else -120.0,
        snr=float(snr) if snr is not None else 0.0,
        frequency_mhz=0.0,
        spreading_factor=0,
        bandwidth_khz=0.0,
        coding_rate="N/A",
    )


def _make_json_safe(payload: dict) -> dict:
    """Convert bytes values to hex strings for JSON serialisation."""
    safe: dict = {}
    for key, val in payload.items():
        if isinstance(val, bytes):
            safe[key] = val.hex()
        elif isinstance(val, dict):
            safe[key] = _make_json_safe(val)
        else:
            safe[key] = val
    return safe
