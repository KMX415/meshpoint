from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles

from src.analytics.network_mapper import NetworkMapper
from src.analytics.signal_analyzer import SignalAnalyzer
from src.analytics.traffic_monitor import TrafficMonitor
from src.api.routes import analytics, device, nodes, packets, system_metrics, telemetry, update_check
from src.api.upstream_client import UpstreamClient
from src.api.websocket_manager import WebSocketManager
from src.config import AppConfig, load_config, validate_activation
from src.coordinator import PipelineCoordinator
from src.log_format import print_banner, print_packet, setup_logging
from src.models.device_identity import DeviceIdentity, _stable_device_id
from src.models.packet import Packet

setup_logging()
logger = logging.getLogger(__name__)

ws_manager = WebSocketManager()
pipeline: PipelineCoordinator | None = None
upstream: UpstreamClient | None = None


def create_app(config: AppConfig | None = None) -> FastAPI:
    if config is None:
        config = load_config()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        global pipeline, upstream
        validate_activation(config)
        identity = DeviceIdentity(
            device_id=_stable_device_id(config.device.device_id),
            device_name=config.device.device_name,
            latitude=config.device.latitude,
            longitude=config.device.longitude,
            altitude=config.device.altitude,
            hardware_description=config.device.hardware_description,
            firmware_version=config.device.firmware_version,
        )
        pipeline = _build_pipeline(config)
        pipeline.on_packet(_on_packet_received)
        pipeline.on_packet(lambda pkt: print_packet(pkt))
        await pipeline.start()

        upstream = UpstreamClient(config.upstream, identity)
        pipeline.on_packet(upstream.send_packet)
        await upstream.start()

        _init_routes(pipeline, config, identity)
        print_banner(config)
        logger.info("Mesh Point started -- listening for packets")
        yield
        await upstream.stop()
        await pipeline.stop()
        logger.info("Mesh Point stopped")

    app = FastAPI(
        title="Mesh Radar - Mesh Point",
        version="0.1.0",
        lifespan=lifespan,
    )

    app.include_router(nodes.router)
    app.include_router(packets.router)
    app.include_router(analytics.router)
    app.include_router(device.router)
    app.include_router(system_metrics.router)
    app.include_router(telemetry.router)
    app.include_router(update_check.router)

    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket):
        await ws_manager.connect(websocket)
        try:
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            await ws_manager.disconnect(websocket)

    static_dir = Path(config.dashboard.static_dir)
    if static_dir.exists():
        app.mount("/", StaticFiles(directory=str(static_dir), html=True))

    return app


def _build_pipeline(config: AppConfig) -> PipelineCoordinator:
    coordinator = PipelineCoordinator(config)

    for source_name in config.capture.sources:
        if source_name == "serial":
            _add_serial_source(coordinator, config)
        elif source_name == "concentrator":
            _add_concentrator_source(coordinator, config)
        elif source_name == "meshcore_usb":
            _add_meshcore_usb_source(coordinator, config)

    if (
        "meshcore_usb" not in config.capture.sources
        and config.capture.meshcore_usb.auto_detect
    ):
        _add_meshcore_usb_source(coordinator, config)

    return coordinator


def _add_serial_source(coordinator: PipelineCoordinator, config: AppConfig):
    try:
        from src.capture.serial_source import SerialCaptureSource
        coordinator.capture_coordinator.add_source(
            SerialCaptureSource(
                port=config.capture.serial_port,
                baud=config.capture.serial_baud,
            )
        )
    except ImportError:
        logger.warning("Serial capture unavailable")


def _add_concentrator_source(
    coordinator: PipelineCoordinator, config: AppConfig
):
    try:
        from src.capture.concentrator_source import ConcentratorCaptureSource
        coordinator.capture_coordinator.add_source(
            ConcentratorCaptureSource(
                spi_path=config.capture.concentrator_spi_device,
                syncword=config.radio.sync_word,
                radio_config=config.radio,
            )
        )
    except Exception:
        logger.exception("Concentrator source unavailable")


def _add_meshcore_usb_source(
    coordinator: PipelineCoordinator, config: AppConfig
):
    try:
        from src.capture.meshcore_usb_source import MeshcoreUsbCaptureSource
        usb_cfg = config.capture.meshcore_usb
        coordinator.capture_coordinator.add_source(
            MeshcoreUsbCaptureSource(
                serial_port=usb_cfg.serial_port,
                baud_rate=usb_cfg.baud_rate,
                auto_detect=usb_cfg.auto_detect,
            )
        )
    except ImportError:
        logger.warning(
            "MeshCore USB unavailable -- meshcore package not installed"
        )


def _init_routes(
    coord: PipelineCoordinator,
    config: AppConfig,
    identity: DeviceIdentity,
) -> None:
    network_mapper = NetworkMapper(coord.node_repo)
    signal_analyzer = SignalAnalyzer(coord.packet_repo)
    traffic_monitor = TrafficMonitor(coord.packet_repo)

    nodes.init_routes(coord.node_repo, network_mapper)
    packets.init_routes(coord.packet_repo)
    analytics.init_routes(signal_analyzer, traffic_monitor, coord.packet_repo)
    device.init_routes(identity, ws_manager, coord.relay_manager)
    telemetry.init_routes(coord.telemetry_repo)


def _on_packet_received(packet: Packet) -> None:
    import asyncio
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(ws_manager.broadcast("packet", packet.to_dict()))
    except RuntimeError:
        pass
