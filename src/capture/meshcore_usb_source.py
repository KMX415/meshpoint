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

_HEALTH_CHECK_INTERVAL_SECONDS = 120
_RECONNECT_BASE_DELAY_SECONDS = 5
_RECONNECT_MAX_DELAY_SECONDS = 60


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

    @property
    def name(self) -> str:
        return "meshcore_usb"

    @property
    def is_running(self) -> bool:
        return self._running

    async def start(self) -> None:
        port = await self._resolve_port()
        if port is None:
            logger.warning(
                "No MeshCore USB device found -- source disabled"
            )
            return

        self._resolved_port = port
        self._running = True
        await self._connect(port)

        if self._connected:
            self._health_task = asyncio.create_task(
                self._health_check_loop(), name="meshcore-health"
            )

    async def stop(self) -> None:
        self._running = False
        if self._health_task:
            self._health_task.cancel()
            try:
                await self._health_task
            except asyncio.CancelledError:
                pass
            self._health_task = None
        await self._disconnect()
        logger.info("MeshCore USB source stopped")

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
                port, self._baud_rate
            )
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
        """Disconnect, wait with backoff, and reconnect."""
        await self._disconnect()
        delay = _RECONNECT_BASE_DELAY_SECONDS

        while self._running:
            logger.info(
                "MeshCore USB reconnecting in %ds...", delay
            )
            await asyncio.sleep(delay)
            if not self._running:
                return

            await self._connect(self._resolved_port)
            if self._connected:
                logger.info("MeshCore USB reconnected successfully")
                return

            delay = min(delay * 2, _RECONNECT_MAX_DELAY_SECONDS)

    async def _health_check_loop(self) -> None:
        """Periodically verify the serial companion is still responding."""
        try:
            while self._running and self._connected:
                await asyncio.sleep(_HEALTH_CHECK_INTERVAL_SECONDS)
                if not self._running:
                    return
                if not await self._check_health():
                    logger.warning(
                        "MeshCore USB health check failed -- reconnecting"
                    )
                    await self._reconnect()
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.exception("MeshCore USB health check loop error")

    async def _check_health(self) -> bool:
        """Send a device query and verify we get a response."""
        if not self._meshcore:
            return False
        try:
            from meshcore import EventType

            result = await asyncio.wait_for(
                self._meshcore.commands.send_device_query(),
                timeout=10.0,
            )
            return result.type != EventType.ERROR
        except Exception:
            return False

    async def _on_event(self, event) -> None:
        if not self._running:
            return
        try:
            self._queue.put_nowait(event)
        except asyncio.QueueFull:
            logger.warning("MeshCore USB queue full, dropping event")

    def _wrap_event(self, event) -> Optional[RawCapture]:
        """Serialise a meshcore Event into a RawCapture envelope."""
        payload_dict = (
            event.payload if isinstance(event.payload, dict) else {}
        )
        envelope = {
            "event_type": (
                event.type.value
                if hasattr(event.type, "value")
                else str(event.type)
            ),
            "payload": _make_json_safe(payload_dict),
        }
        return RawCapture(
            payload=json.dumps(envelope).encode("utf-8"),
            signal=_extract_signal(payload_dict),
            capture_source="meshcore_usb",
            protocol_hint=Protocol.MESHCORE,
        )

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
