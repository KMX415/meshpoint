"""Capture Meshtastic packets from a local meshtasticd TCP bridge."""

from __future__ import annotations

import asyncio
import logging
from typing import AsyncIterator, Optional

from src.capture.base import CaptureSource
from src.capture.meshtastic_packet_adapter import packet_dict_to_raw_capture
from src.capture.meshtasticd_config_sync import (
    MeshtasticdSyncSettings,
    sync_meshtasticd_config,
)
from src.models.packet import RawCapture

logger = logging.getLogger(__name__)

_DEFAULT_CONNECT_ATTEMPTS = 30
_DEFAULT_CONNECT_DELAY_SECONDS = 2.0


class MeshtasticdBridgeSource(CaptureSource):
    """Receive packets from meshtasticd over TCP (default port 4403).

    meshtasticd owns the WisBlock SX1262 radio on WisMesh Node platforms.
    Meshpoint connects as a client and feeds the normal decode pipeline.
    """

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 4403,
        default_frequency_mhz: float = 906.875,
        connect_attempts: int = _DEFAULT_CONNECT_ATTEMPTS,
        connect_delay_seconds: float = _DEFAULT_CONNECT_DELAY_SECONDS,
        sync_settings: MeshtasticdSyncSettings | None = None,
    ):
        self._host = host
        self._port = port
        self._default_frequency_mhz = default_frequency_mhz
        self._connect_attempts = connect_attempts
        self._connect_delay_seconds = connect_delay_seconds
        self._sync_settings = sync_settings
        self._interface = None
        self._running = False
        self._loop: asyncio.AbstractEventLoop | None = None
        self._queue: asyncio.Queue[RawCapture] = asyncio.Queue(maxsize=500)

    @property
    def name(self) -> str:
        return "meshtasticd"

    @property
    def is_running(self) -> bool:
        return self._running and self._interface is not None

    @property
    def interface(self):
        """Live meshtastic TCPInterface handle for outbound TX."""
        return self._interface

    async def start(self) -> None:
        self._loop = asyncio.get_running_loop()
        last_error: Optional[Exception] = None
        for attempt in range(1, self._connect_attempts + 1):
            try:
                self._running = True
                await asyncio.to_thread(self._connect_blocking)
                if self._sync_settings is not None:
                    await asyncio.to_thread(
                        sync_meshtasticd_config,
                        self._interface,
                        self._sync_settings,
                    )
                logger.info(
                    "meshtasticd bridge connected to %s:%d",
                    self._host,
                    self._port,
                )
                return
            except Exception as exc:
                self._running = False
                last_error = exc
                logger.warning(
                    "meshtasticd bridge connect attempt %d/%d failed: %s",
                    attempt,
                    self._connect_attempts,
                    exc,
                )
                await asyncio.sleep(self._connect_delay_seconds)

        raise RuntimeError(
            f"Could not connect to meshtasticd at {self._host}:{self._port}"
        ) from last_error

    def _connect_blocking(self) -> None:
        import meshtastic.tcp_interface
        from pubsub import pub

        if self._interface is not None:
            try:
                self._interface.close()
            except Exception:
                pass
            self._interface = None

        self._interface = meshtastic.tcp_interface.TCPInterface(
            hostname=self._host,
            portNumber=self._port,
            connectNow=True,
        )
        pub.subscribe(self._on_receive, "meshtastic.receive")

    async def stop(self) -> None:
        self._running = False
        if self._interface is not None:
            try:
                from pubsub import pub

                pub.unsubscribe(self._on_receive, "meshtastic.receive")
            except Exception:
                pass
            try:
                await asyncio.to_thread(self._interface.close)
            except Exception:
                logger.debug("meshtasticd bridge close failed", exc_info=True)
            self._interface = None
        logger.info("meshtasticd bridge stopped")

    async def packets(self) -> AsyncIterator[RawCapture]:
        while self._running:
            try:
                raw = await asyncio.wait_for(self._queue.get(), timeout=1.0)
                yield raw
            except asyncio.TimeoutError:
                continue

    def _on_receive(self, packet, interface) -> None:
        if not self._running:
            return
        try:
            raw_capture = packet_dict_to_raw_capture(
                packet,
                capture_source="meshtasticd",
                default_frequency_mhz=self._default_frequency_mhz,
            )
            if raw_capture:
                self._enqueue(raw_capture)
        except Exception:
            logger.debug("Failed to convert meshtasticd packet", exc_info=True)

    def _enqueue(self, raw_capture: RawCapture) -> None:
        """Thread-safe handoff from meshtastic-python reader to asyncio."""
        loop = self._loop
        if loop is None or not loop.is_running():
            return
        try:
            loop.call_soon_threadsafe(self._queue.put_nowait, raw_capture)
        except asyncio.QueueFull:
            logger.warning("meshtasticd capture queue full")
