from __future__ import annotations

import asyncio
import logging
from typing import Callable, Optional

from src.capture.capture_coordinator import CaptureCoordinator
from src.config import AppConfig
from src.decode.crypto_service import CryptoService
from src.decode.packet_router import PacketRouter
from src.log_format import CYAN, DIM, GREEN, RESET
from src.models.packet import Packet, Protocol, RawCapture
from src.relay.meshtastic_transmitter import MeshtasticTransmitter
from src.relay.relay_manager import RelayManager
from src.storage.database import DatabaseManager
from src.storage.node_repository import NodeRepository
from src.storage.packet_repository import PacketRepository
from src.storage.telemetry_repository import TelemetryRepository

logger = logging.getLogger(__name__)

_SOURCE_LABELS = {
    "concentrator": "concentrator (8-ch SX1302)",
    "serial": "serial radio",
    "mock": "mock source",
}


class PipelineCoordinator:
    """Wires the full capture -> decode -> store -> broadcast pipeline."""

    def __init__(self, config: AppConfig):
        self._config = config

        self._db = DatabaseManager(config.storage.database_path)
        self._crypto = CryptoService(config.meshtastic.default_key_b64)
        self._router = PacketRouter(self._crypto)
        self._capture = CaptureCoordinator()
        relay_cfg = config.relay
        self._relay = RelayManager(
            enabled=relay_cfg.enabled,
            max_relay_per_minute=relay_cfg.max_relay_per_minute,
            burst_size=relay_cfg.burst_size,
            min_relay_rssi=relay_cfg.min_relay_rssi,
            max_relay_rssi=relay_cfg.max_relay_rssi,
        )
        self._transmitter: Optional[MeshtasticTransmitter] = None

        self._node_repo: Optional[NodeRepository] = None
        self._packet_repo: Optional[PacketRepository] = None
        self._telemetry_repo: Optional[TelemetryRepository] = None

        self._on_packet_callbacks: list[Callable[[Packet], None]] = []
        self._running = False
        self._pipeline_task: Optional[asyncio.Task] = None
        self._cleanup_task: Optional[asyncio.Task] = None

    @property
    def database(self) -> DatabaseManager:
        return self._db

    @property
    def node_repo(self) -> NodeRepository:
        if self._node_repo is None:
            raise RuntimeError("Pipeline not started")
        return self._node_repo

    @property
    def packet_repo(self) -> PacketRepository:
        if self._packet_repo is None:
            raise RuntimeError("Pipeline not started")
        return self._packet_repo

    @property
    def telemetry_repo(self) -> TelemetryRepository:
        if self._telemetry_repo is None:
            raise RuntimeError("Pipeline not started")
        return self._telemetry_repo

    @property
    def capture_coordinator(self) -> CaptureCoordinator:
        return self._capture

    @property
    def relay_manager(self) -> RelayManager:
        return self._relay

    def on_packet(self, callback: Callable[[Packet], None]) -> None:
        """Register a callback invoked for each decoded packet."""
        self._on_packet_callbacks.append(callback)

    async def start(self) -> None:
        await self._db.connect()
        self._node_repo = NodeRepository(self._db)
        self._packet_repo = PacketRepository(self._db)
        self._telemetry_repo = TelemetryRepository(self._db)

        self._setup_channel_keys()
        self._setup_relay_transmitter()
        await self._capture.start()

        self._running = True
        self._pipeline_task = asyncio.create_task(
            self._run_pipeline(), name="pipeline"
        )
        self._cleanup_task = asyncio.create_task(
            self._cleanup_loop(), name="db-cleanup"
        )
        sources = ", ".join(
            _SOURCE_LABELS.get(s, s) for s in self._config.capture.sources
        )
        logger.info(
            f" {CYAN}--{RESET} {GREEN}PIPELINE{RESET}  started  "
            f"{DIM}sources: {sources}{RESET}"
        )

    async def stop(self) -> None:
        self._running = False
        await self._capture.stop()
        for task in (self._pipeline_task, self._cleanup_task):
            if task:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        if self._transmitter:
            self._transmitter.disconnect()
        await self._db.disconnect()
        logger.info(
            f" {CYAN}--{RESET} {DIM}PIPELINE{RESET}  stopped"
        )

    async def _cleanup_loop(self) -> None:
        """Periodically prune old packets to keep the DB from growing unbounded."""
        interval = self._config.storage.cleanup_interval_seconds
        max_retained = self._config.storage.max_packets_retained
        try:
            while self._running:
                await asyncio.sleep(interval)
                removed = await self._packet_repo.cleanup_old(max_retained)
                if removed:
                    logger.info(
                        f" {CYAN}--{RESET} {DIM}CLEANUP{RESET}  "
                        f"pruned {removed} old packets  "
                        f"{DIM}(max {max_retained}){RESET}"
                    )
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.exception("Cleanup loop error")

    async def _run_pipeline(self) -> None:
        try:
            async for raw_capture in self._capture.packets():
                if not self._running:
                    break
                await self._process_capture(raw_capture)
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.exception("Pipeline error")

    async def _process_capture(self, raw: RawCapture) -> None:
        packet = self._router.decode(
            raw.payload, signal=raw.signal, protocol_hint=raw.protocol_hint
        )
        if packet is None:
            return

        packet.capture_source = raw.capture_source
        await self._store_packet(packet)
        await self._relay.process_packet(packet)
        self._notify_callbacks(packet)

    async def _store_packet(self, packet: Packet) -> None:
        try:
            await self._packet_repo.insert(packet)
            await self._update_node(packet)
            await self._store_telemetry(packet)
        except Exception:
            logger.exception("Failed to store packet %s", packet.packet_id)

    async def _update_node(self, packet: Packet) -> None:
        decoder = (
            self._router.meshtastic_decoder
            if packet.protocol == Protocol.MESHTASTIC
            else self._router.meshcore_decoder
        )
        node_update = decoder.extract_node_update(packet)
        if node_update:
            await self._node_repo.upsert(node_update)

    async def _store_telemetry(self, packet: Packet) -> None:
        decoder = (
            self._router.meshtastic_decoder
            if packet.protocol == Protocol.MESHTASTIC
            else self._router.meshcore_decoder
        )
        telemetry = decoder.extract_telemetry(packet)
        if telemetry:
            await self._telemetry_repo.insert(telemetry)

    def _notify_callbacks(self, packet: Packet) -> None:
        for callback in self._on_packet_callbacks:
            try:
                callback(packet)
            except Exception:
                logger.exception("Packet callback error")

    def _setup_relay_transmitter(self) -> None:
        if not self._config.relay.enabled:
            logger.info(
                f" {CYAN}--{RESET} {DIM}RELAY{RESET}    disabled"
            )
            return

        self._transmitter = MeshtasticTransmitter(self._config.relay)
        self._transmitter.connect()
        self._relay.set_transmit_function(self._transmitter.transmit)
        logger.info(
            f" {CYAN}--{RESET} {GREEN}RELAY{RESET}    "
            f"transmitter ready  "
            f"{DIM}max {self._config.relay.max_relay_per_minute}/min{RESET}"
        )

    def _setup_channel_keys(self) -> None:
        for name, key in self._config.meshtastic.channel_keys.items():
            self._crypto.add_channel_key(name, key)
        for name, key in self._config.meshcore.channel_keys.items():
            self._crypto.add_channel_key(name, key)
