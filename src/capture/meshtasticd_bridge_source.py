"""Capture Meshtastic packets from a local meshtasticd TCP bridge."""

from __future__ import annotations

import asyncio
import logging
import multiprocessing as mp
import queue
import time
from dataclasses import asdict
from typing import Any, AsyncIterator, Optional

from src.capture.base import CaptureSource
from src.capture.meshtasticd_bridge_ipc import (
    BridgeCommand,
    BridgeResponse,
    fatal_reason,
    is_fatal_message,
)
from src.capture.meshtasticd_bridge_worker import run_bridge_worker
from src.capture.meshtasticd_config_sync import MeshtasticdSyncSettings
from src.capture.meshtasticd_daemon import wait_for_tcp_port
from src.models.packet import RawCapture

logger = logging.getLogger(__name__)

_DEFAULT_CONNECT_ATTEMPTS = 30
_DEFAULT_CONNECT_DELAY_SECONDS = 2.0
_WORKER_READY_TIMEOUT_SECONDS = 90.0
_TX_RESPONSE_TIMEOUT_SECONDS = 30.0


class MeshtasticdBridgeSource(CaptureSource):
    """Receive packets from meshtasticd via a dedicated bridge worker process.

    meshtasticd allows only one Phone API client with global stream state.
    meshtastic-python's TCP reader must not share a process with uvicorn or
    be torn down and recreated in-process. The worker owns the TCP session for
    the lifetime of this capture source.
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
        self._ctx = mp.get_context("spawn")
        self._pkt_queue: mp.Queue | None = None
        self._cmd_queue: mp.Queue | None = None
        self._resp_queue: mp.Queue | None = None
        self._worker: mp.Process | None = None
        self._running = False
        self._connected_at: float = 0.0
        self._packets_received: int = 0
        self._local_node_id_hex: str | None = None

    @property
    def name(self) -> str:
        return "meshtasticd"

    @property
    def is_running(self) -> bool:
        return (
            self._running
            and self._worker is not None
            and self._worker.is_alive()
        )

    @property
    def interface(self):
        """Deprecated: TX goes through request_send_text/request_send_nodeinfo."""
        return None

    @property
    def local_node_id_hex(self) -> str | None:
        """Meshtastic node id owned by meshtasticd (8-char lowercase hex)."""
        return self._local_node_id_hex

    async def start(self) -> None:
        last_error: Optional[Exception] = None
        for attempt in range(1, self._connect_attempts + 1):
            try:
                await asyncio.to_thread(wait_for_tcp_port, self._host, self._port)
                await asyncio.to_thread(self._start_worker)
                self._running = True
                self._connected_at = time.monotonic()
                logger.info(
                    "meshtasticd bridge connected to %s:%d (worker pid=%s)",
                    self._host,
                    self._port,
                    self._worker.pid if self._worker else "?",
                )
                return
            except Exception as exc:
                self._stop_worker()
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

    def _start_worker(self) -> None:
        self._pkt_queue = self._ctx.Queue(maxsize=500)
        self._cmd_queue = self._ctx.Queue()
        self._resp_queue = self._ctx.Queue()
        sync_dict = (
            asdict(self._sync_settings) if self._sync_settings is not None else None
        )
        self._worker = self._ctx.Process(
            target=run_bridge_worker,
            args=(
                self._host,
                self._port,
                self._default_frequency_mhz,
                self._pkt_queue,
                self._cmd_queue,
                self._resp_queue,
                sync_dict,
            ),
            name="meshtasticd-bridge",
            daemon=True,
        )
        self._worker.start()
        self._await_worker_ready()

    def _await_worker_ready(self) -> None:
        if self._resp_queue is None:
            raise RuntimeError("bridge response queue missing")
        try:
            status, detail = self._resp_queue.get(timeout=_WORKER_READY_TIMEOUT_SECONDS)
        except queue.Empty as exc:
            raise TimeoutError("meshtasticd bridge worker did not become ready") from exc
        if status != BridgeResponse.READY:
            raise RuntimeError(f"meshtasticd bridge worker failed to start: {detail}")
        if isinstance(detail, str) and detail:
            self._local_node_id_hex = detail.lower()

    async def stop(self) -> None:
        self._running = False
        if self._cmd_queue is not None:
            try:
                self._cmd_queue.put((BridgeCommand.STOP, None))
            except Exception:
                logger.debug("meshtasticd bridge stop command failed", exc_info=True)
        self._stop_worker()
        logger.info("meshtasticd bridge stopped")

    def _stop_worker(self) -> None:
        worker = self._worker
        self._worker = None
        if worker is not None and worker.is_alive():
            worker.join(timeout=10.0)
            if worker.is_alive():
                worker.terminate()
                worker.join(timeout=5.0)
        self._pkt_queue = None
        self._cmd_queue = None
        self._resp_queue = None

    async def packets(self) -> AsyncIterator[RawCapture]:
        while self._running:
            if self._worker is not None and not self._worker.is_alive():
                raise RuntimeError("meshtasticd bridge worker exited unexpectedly")
            try:
                raw = await asyncio.to_thread(
                    self._pkt_queue.get,
                    True,
                    1.0,
                )
            except queue.Empty:
                continue
            if is_fatal_message(raw):
                raise RuntimeError(fatal_reason(raw))
            self._packets_received += 1
            yield raw

    def request_send_text(
        self,
        text: str,
        destination: int,
        channel: int = 0,
        want_ack: bool = False,
    ) -> tuple[bool, str | None]:
        return self._request(
            BridgeCommand.SEND_TEXT,
            {
                "text": text,
                "destination": destination,
                "channel": channel,
                "want_ack": want_ack,
            },
        )

    def request_send_nodeinfo(
        self,
        long_name: str,
        short_name: str,
        hw_model: int = 37,
    ) -> tuple[bool, str | None]:
        return self._request(
            BridgeCommand.SEND_NODEINFO,
            {
                "long_name": long_name,
                "short_name": short_name,
                "hw_model": hw_model,
            },
        )

    def request_read_radio_state(self) -> tuple[bool, dict | str | None]:
        """Return live owner + LoRa prefs from the bridge worker."""
        return self._request(BridgeCommand.READ_RADIO_STATE, {})

    def request_write_lora(self, payload: dict) -> tuple[bool, dict | str | None]:
        return self._request(BridgeCommand.WRITE_LORA, payload)

    def request_write_owner(
        self,
        long_name: str,
        short_name: str,
        hw_model: int = 37,
    ) -> tuple[bool, str | None]:
        return self._request(
            BridgeCommand.WRITE_OWNER,
            {
                "long_name": long_name,
                "short_name": short_name,
                "hw_model": hw_model,
            },
        )

    def _request(
        self, command: BridgeCommand, payload: dict
    ) -> tuple[bool, Any]:
        if self._cmd_queue is None or self._resp_queue is None:
            return False, "meshtasticd bridge not connected"
        self._cmd_queue.put((command, payload))
        try:
            status, detail = self._resp_queue.get(timeout=_TX_RESPONSE_TIMEOUT_SECONDS)
        except queue.Empty:
            return False, "meshtasticd bridge command timed out"
        if status == BridgeResponse.OK:
            return True, detail
        return False, str(detail or "meshtasticd bridge command failed")
