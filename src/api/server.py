from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from src._so_compat_check import warn_if_stale_so_files
from src.analytics.network_mapper import NetworkMapper
from src.analytics.signal_analyzer import SignalAnalyzer
from src.analytics.traffic_monitor import TrafficMonitor
from src.api.audit import AuditLogWriter
from src.api.audit import dependencies as audit_deps
from src.api.auth import dependencies as auth_deps
from src.api.auth.auth_bootstrap import AuthSubsystem, build_auth_subsystem
from src.api.auth.dependencies import SESSION_COOKIE_NAME, require_auth
from src.api.auth.jwt_session import JwtSessionService
from src.api.auth.ws_guard import WS_AUTH_CLOSE_CODE, authenticate_websocket
from src.api.dangerous import DangerousActionRegistry
from src.api.dangerous.handlers import (
    build_clear_database_action,
    build_force_nodeinfo_action,
    build_restart_concentrator_action,
    build_restart_service_action,
    build_wipe_phantoms_action,
)
from src.api.meshcore_contacts import (
    log_meshcore_contact_peers,
    schedule_startup_meshcore_contact_sync,
    setup_meshcore_contact_enrichment,
    sync_meshcore_contacts_to_nodes,
)
from src.api.routes import (
    analytics,
    auth_config_routes,
    auth_routes,
    config_routes,
    dangerous_routes,
    device,
    device_config_routes,
    gps_status,
    identity_routes,
    messages,
    meshcore_config_routes,
    mqtt_config_routes,
    nodeinfo_routes,
    nodes,
    packets,
    public_radar_routes,
    stats_routes,
    system_config_routes,
    system_metrics,
    telemetry,
    terminal_routes,
    upstream_config_routes,
    update_check,
    update_routes,
)
from src.api.terminal import CommandCatalog, SessionManager
from src.api.update import ReleaseChannelRegistry, UpdateApplier
from src.api.update.rollback_state import resolve_rollback_state_path
from src.api.upstream_client import UpstreamClient
from src.api.websocket_manager import WebSocketManager
from src.config import AppConfig, load_config, validate_activation
from src.coordinator import PipelineCoordinator
from src.log_format import print_banner, print_packet, setup_logging
from src.models.device_identity import DeviceIdentity, _stable_device_id
from src.models.packet import Packet
from src.storage.message_repository import MessageRepository
from src.api.telemetry.noise_floor import NoiseFloorTracker
from src.api.telemetry.spectral_scan_service import SpectralScanService
from src.transmit.nodeinfo_broadcaster import (
    NodeInfoBroadcaster,
    clamp_interval_minutes,
)
from src.transmit.position_broadcaster import PositionBroadcaster
from src.transmit.telemetry_broadcaster import TelemetryBroadcaster
from src.transmit.meshtastic_inbound_handler import MeshtasticInboundHandler
from src.transmit.tx_service import TxService
from src.version import __version__

setup_logging()
logger = logging.getLogger(__name__)

ws_manager = WebSocketManager()
pipeline: PipelineCoordinator | None = None
upstream: UpstreamClient | None = None
nodeinfo_broadcaster: NodeInfoBroadcaster | None = None
telemetry_broadcaster: TelemetryBroadcaster | None = None
position_broadcaster: PositionBroadcaster | None = None
noise_floor_tracker = NoiseFloorTracker()
_noise_floor_emitter_task = None
_spectral_scan_service: SpectralScanService | None = None


def create_app(config: AppConfig | None = None) -> FastAPI:
    if config is None:
        config = load_config()

    auth_subsystem = build_auth_subsystem(config)
    auth_routes.init_routes(auth_subsystem.service)
    auth_config_routes.init_routes(auth_subsystem.service)
    auth_deps.init_auth(auth_subsystem.jwt_service)
    audit_writer = AuditLogWriter()
    audit_deps.init_audit(audit_writer)
    session_manager = SessionManager(cwd="/opt/meshpoint")
    terminal_routes.init_routes(
        session_manager=session_manager,
        command_catalog=CommandCatalog(),
        jwt_service=auth_subsystem.jwt_service,
        audit_writer=audit_writer,
    )
    update_routes.init_routes(
        applier=UpdateApplier(
            rollback_state_path=resolve_rollback_state_path(
                config.storage.database_path,
            ),
        ),
        registry=ReleaseChannelRegistry(),
        changelog_path=Path(__file__).resolve().parents[2] / "docs" / "CHANGELOG.md",
        rollback_state_path=resolve_rollback_state_path(
            config.storage.database_path,
        ),
    )
    # Dangerous registry is wired in lifespan so clear-db / wipe-phantoms /
    # force-nodeinfo can close over the live pipeline objects.

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        global pipeline, upstream, nodeinfo_broadcaster
        global telemetry_broadcaster, position_broadcaster
        warn_if_stale_so_files()
        validate_activation(config)
        identity = DeviceIdentity(
            device_id=_stable_device_id(config.device.device_id),
            device_name=config.device.device_name,
            long_name=config.transmit.long_name,
            short_name=config.transmit.short_name,
            latitude=config.device.latitude,
            longitude=config.device.longitude,
            altitude=config.device.altitude,
            hardware_description=config.device.hardware_description,
            firmware_version=config.device.firmware_version,
        )
        pipeline = _build_pipeline(config)
        pipeline.on_packet(_on_packet_received)
        pipeline.on_packet(lambda pkt: print_packet(pkt))
        pipeline.on_packet(public_radar_routes.public_radar_packet_callback)

        if config.transmit.enabled:
            _inject_tx_gain_into_source(pipeline)

        _bootstrap_pki(config, pipeline)
        await _hydrate_public_keys(pipeline)

        await pipeline.start()

        message_repo = MessageRepository(pipeline.database)
        tx_service = _build_tx_service(config, pipeline)
        mc_source = _find_meshcore_source(pipeline)
        meshcore_tx_ref = None
        if tx_service and hasattr(tx_service, '_meshcore_tx'):
            meshcore_tx_ref = tx_service._meshcore_tx
            if meshcore_tx_ref and meshcore_tx_ref.connected:
                import asyncio
                asyncio.get_running_loop().create_task(
                    _send_meshcore_advert(meshcore_tx_ref, mc_source)
                )
        _setup_message_interception(
            pipeline, message_repo, config, meshcore_tx_ref, tx_service
        )
        _setup_inbound_responder(pipeline, tx_service, config)
        setup_meshcore_contact_enrichment(pipeline, meshcore_tx_ref)
        if meshcore_tx_ref and meshcore_tx_ref.connected:
            import asyncio
            loop = asyncio.get_running_loop()
            loop.create_task(
                sync_meshcore_contacts_to_nodes(pipeline, meshcore_tx_ref)
            )
            schedule_startup_meshcore_contact_sync(
                loop, pipeline, meshcore_tx_ref, mc_source
            )

        upstream = UpstreamClient(
            config.upstream, identity,
            stats_reporter=pipeline.stats_reporter,
        )
        pipeline.on_packet(upstream.send_packet)
        await upstream.start()

        nodeinfo_broadcaster = _build_nodeinfo_broadcaster(config, tx_service)
        if nodeinfo_broadcaster is not None:
            await nodeinfo_broadcaster.start()

        telemetry_broadcaster = _build_telemetry_broadcaster(
            config, tx_service, pipeline
        )
        if telemetry_broadcaster is not None:
            await telemetry_broadcaster.start()

        position_broadcaster = _build_position_broadcaster(
            config, tx_service, pipeline
        )
        if position_broadcaster is not None:
            await position_broadcaster.start()

        _wire_native_relay(pipeline, tx_service)

        global _noise_floor_emitter_task
        import asyncio
        _noise_floor_emitter_task = asyncio.get_running_loop().create_task(
            _noise_floor_emitter_loop(noise_floor_tracker, ws_manager)
        )

        global _spectral_scan_service
        _spectral_scan_service = _build_spectral_scan_service(
            pipeline, config, noise_floor_tracker,
        )
        if _spectral_scan_service is not None:
            await _spectral_scan_service.start()

        _init_routes(
            pipeline, config, identity, auth_subsystem, tx_service, message_repo
        )
        _init_dangerous_registry(pipeline)
        print_banner(config)
        logger.info("Meshpoint started -- listening for packets")
        yield
        if _spectral_scan_service is not None:
            await _spectral_scan_service.stop()
        if _noise_floor_emitter_task is not None:
            _noise_floor_emitter_task.cancel()
            try:
                await _noise_floor_emitter_task
            except BaseException:
                pass
        if nodeinfo_broadcaster is not None:
            await nodeinfo_broadcaster.stop()
        if telemetry_broadcaster is not None:
            await telemetry_broadcaster.stop()
        if position_broadcaster is not None:
            await position_broadcaster.stop()
        await upstream.stop()
        await pipeline.stop()
        session_manager.shutdown()
        logger.info("Meshpoint stopped")

    app = FastAPI(
        title="Meshpoint",
        version=__version__,
        lifespan=lifespan,
    )

    app.include_router(auth_routes.router)
    app.include_router(identity_routes.router)
    app.include_router(auth_config_routes.router)
    app.include_router(public_radar_routes.router)
    app.include_router(terminal_routes.router)
    app.include_router(update_routes.router)
    app.include_router(dangerous_routes.router)

    protected = [Depends(require_auth)]
    app.include_router(nodes.router, dependencies=protected)
    app.include_router(packets.router, dependencies=protected)
    app.include_router(analytics.router, dependencies=protected)
    app.include_router(device.router, dependencies=protected)
    app.include_router(system_metrics.router, dependencies=protected)
    app.include_router(telemetry.router, dependencies=protected)
    app.include_router(update_check.router, dependencies=protected)
    app.include_router(messages.router, dependencies=protected)
    app.include_router(nodeinfo_routes.router, dependencies=protected)
    app.include_router(mqtt_config_routes.router, dependencies=protected)
    app.include_router(upstream_config_routes.router, dependencies=protected)
    app.include_router(device_config_routes.router, dependencies=protected)
    app.include_router(gps_status.router, dependencies=protected)
    app.include_router(system_config_routes.router, dependencies=protected)
    app.include_router(meshcore_config_routes.router, dependencies=protected)
    app.include_router(config_routes.router, dependencies=protected)
    app.include_router(stats_routes.router, dependencies=protected)

    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket):
        if not await _gate_ws_or_close(
            websocket, auth_subsystem.jwt_service
        ):
            return
        await ws_manager.connect(websocket)
        try:
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            await ws_manager.disconnect(websocket)

    static_dir = Path(config.dashboard.static_dir)

    @app.get("/setup", include_in_schema=False)
    async def serve_setup_page():
        return _serve_auth_page(static_dir, "setup.html")

    @app.get("/login", include_in_schema=False)
    async def serve_login_page():
        return _serve_auth_page(static_dir, "login.html")

    @app.get("/", include_in_schema=False)
    async def serve_dashboard_root(request: Request):
        # Gate the dashboard HTML behind auth with a 302 redirect so
        # the browser lands on /login (or /setup) instead of loading
        # cached SPA JS that then fights an unauthenticated /ws upgrade.
        # Registered BEFORE the StaticFiles mount so this route wins.
        if not _request_has_valid_session(
            request, auth_subsystem.jwt_service
        ):
            target = "/login" if auth_subsystem.service.is_setup_complete() else "/setup"
            return RedirectResponse(url=target, status_code=302)
        return FileResponse(
            str(static_dir / "index.html"), media_type="text/html"
        )

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
                sx1261_spi_path=config.radio.sx1261_spi_path,
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


def _resolve_mesh_node_id(config: AppConfig) -> int | None:
    configured = config.transmit.node_id
    if configured is not None:
        return configured
    device_id = (config.device.device_id or "").strip()
    if not device_id:
        return None
    try:
        return TxService._derive_node_id(device_id)
    except RuntimeError:
        return None


def _bootstrap_pki(config: AppConfig, coord: PipelineCoordinator) -> None:
    """Load PKI keypair and wire decoder identity before packet capture starts."""
    from src.identity.keypair import (
        KeypairStore,
        resolve_keypair_path,
        resolve_keypair_path_from_env,
    )

    if not hasattr(coord, "_crypto"):
        return

    coord._crypto.set_node_db_path(config.storage.database_path)
    our_node_id = _resolve_mesh_node_id(config)
    if our_node_id is not None:
        coord._router.meshtastic_decoder.configure_identity(our_node_id)
        logger.info(
            "Meshtastic PKI identity configured: 0x%08x", our_node_id
        )

    override = resolve_keypair_path_from_env()
    key_path = override or resolve_keypair_path(config.storage.database_path)
    try:
        keypair = KeypairStore(key_path).load_or_create()
        coord._crypto.set_keypair(keypair.private_key, keypair.public_key)
        logger.info("Meshtastic PKI keypair loaded from %s", key_path)
    except Exception:
        logger.exception("Failed to load Meshtastic PKI keypair")


async def _hydrate_public_keys(coord: PipelineCoordinator) -> None:
    if not hasattr(coord, "_crypto"):
        return
    await coord.database.connect()
    rows = await coord.database.fetch_all(
        """
        SELECT node_id, public_key FROM nodes
        WHERE public_key IS NOT NULL AND public_key != ''
        LIMIT 5000
        """
    )
    for row in rows:
        node_id = row.get("node_id")
        public_key = row.get("public_key")
        if not node_id or not public_key:
            continue
        try:
            coord._crypto.register_public_key(
                int(node_id, 16),
                bytes.fromhex(public_key),
            )
        except ValueError:
            continue


def _telemetry_metrics_providers(
    tx_service: TxService,
    coord: PipelineCoordinator,
    service_started: float,
    *,
    noise_floor_tracker=None,
    relay_manager=None,
):
    """Shared device_metrics / local_stats snapshots for TX paths."""
    import time

    duty = getattr(tx_service, "_duty", None)
    stats = getattr(coord, "stats_reporter", None)

    def device_metrics() -> dict:
        air_util = duty.current_usage_percent() if duty else 0.0
        return {
            "battery_level": 101,
            "voltage": 5.0,
            "channel_utilization": 0.0,
            "air_util_tx": round(air_util, 2),
            "uptime_seconds": int(time.monotonic() - service_started),
        }

    def local_stats() -> dict:
        dm = device_metrics()
        noise_floor = None
        if noise_floor_tracker is not None:
            snap = noise_floor_tracker.snapshot()
            value_dbm = snap.get("value_dbm")
            if value_dbm is not None:
                noise_floor = int(round(value_dbm))
        relayed = 0
        if relay_manager is not None:
            relayed = int(relay_manager.get_stats().get("relayed", 0))
        return {
            "uptime_seconds": dm["uptime_seconds"],
            "channel_utilization": dm["channel_utilization"],
            "air_util_tx": dm["air_util_tx"],
            "num_packets_tx": 0,
            "num_packets_rx": stats.total_packets if stats else 0,
            "num_packets_rx_bad": 0,
            "num_online_nodes": 0,
            "num_total_nodes": 0,
            "num_tx_relay": relayed,
            "noise_floor": noise_floor,
        }

    return device_metrics, local_stats


def _setup_inbound_responder(
    coord: PipelineCoordinator,
    tx_service: TxService | None,
    config: AppConfig,
) -> None:
    if tx_service is None or not tx_service.meshtastic_enabled:
        return

    import time

    our_node_id = tx_service.source_node_id
    our_node_hex = f"{our_node_id:08x}"
    coord._router.meshtastic_decoder.configure_identity(our_node_id)
    coord.relay_manager.set_local_node_id(our_node_hex)
    device_fn, local_fn = _telemetry_metrics_providers(
        tx_service,
        coord,
        time.monotonic(),
        noise_floor_tracker=noise_floor_tracker,
        relay_manager=coord.relay_manager,
    )
    tx_service.set_telemetry_reply_providers(device_fn, local_fn)
    handler = MeshtasticInboundHandler(tx_service, our_node_id)

    def on_packet(packet: Packet) -> None:
        import asyncio

        try:
            asyncio.get_running_loop().create_task(handler.handle(packet))
        except RuntimeError:
            pass

    coord.on_packet(on_packet)


def _build_telemetry_broadcaster(
    config: AppConfig,
    tx_service: TxService | None,
    coord: PipelineCoordinator,
) -> TelemetryBroadcaster | None:
    if tx_service is None or not tx_service.meshtastic_enabled:
        return None
    telem = config.transmit.telemetry
    if clamp_interval_minutes(telem.interval_minutes) == 0:
        return None

    import time

    service_started = time.monotonic()
    device_fn, _local_fn = _telemetry_metrics_providers(
        tx_service,
        coord,
        service_started,
        noise_floor_tracker=noise_floor_tracker,
        relay_manager=coord.relay_manager,
    )

    return TelemetryBroadcaster(
        tx_service,
        interval_minutes=telem.interval_minutes,
        startup_delay_seconds=telem.startup_delay_seconds,
        metrics_provider=device_fn,
    )


def _build_position_broadcaster(
    config: AppConfig,
    tx_service: TxService | None,
    coord: PipelineCoordinator,
) -> PositionBroadcaster | None:
    if tx_service is None or not tx_service.meshtastic_enabled:
        return None
    pos_cfg = config.transmit.position
    if clamp_interval_minutes(pos_cfg.interval_minutes) == 0:
        return None

    from src.transmit.mesh_position_resolver import MeshPositionResolver

    resolver = MeshPositionResolver(config, coord.location_source)

    return PositionBroadcaster(
        tx_service,
        interval_minutes=pos_cfg.interval_minutes,
        startup_delay_seconds=pos_cfg.startup_delay_seconds,
        coords_provider=resolver.resolve,
    )


def _build_tx_service(
    config: AppConfig, coord: PipelineCoordinator
) -> TxService | None:
    """Build the TX service if transmit is enabled in config."""
    if not config.transmit.enabled:
        logger.info("Transmit disabled in config")
        return None

    from src.transmit.duty_cycle import DutyCycleTracker, resolve_max_duty_percent
    from src.transmit.meshcore_tx_client import MeshCoreTxClient

    duty = DutyCycleTracker(
        region=config.radio.region,
        max_duty_percent=resolve_max_duty_percent(
            config.radio.region,
            config.transmit.max_duty_cycle_percent,
        ),
    )
    meshcore_tx = MeshCoreTxClient()
    mc_source = _find_meshcore_source(coord)
    if mc_source:
        # Bind to the live source so reconnects in the capture path
        # propagate to the dashboard's "MeshCore connected" status and
        # to outbound send commands.
        meshcore_tx.set_source(mc_source)
        meshcore_tx.set_post_command_callback(mc_source.restart_auto_fetching)

        async def _sync_channels_on_connect():
            await meshcore_tx.sync_channels(config.meshcore.channel_keys)
            await _reapply_companion_name(meshcore_tx, config)

        mc_source.set_connected_callback(_sync_channels_on_connect)

    wrapper = _get_concentrator_wrapper(coord)
    crypto = coord._crypto if hasattr(coord, "_crypto") else None
    channel_plan = _get_channel_plan(config)

    tx_svc = TxService(
        wrapper=wrapper,
        crypto=crypto,
        channel_plan=channel_plan,
        transmit_config=config.transmit,
        meshcore_tx=meshcore_tx,
        duty_tracker=duty,
        radio_config=config.radio,
        primary_channel_name=config.meshtastic.primary_channel_name,
        device_id=config.device.device_id,
    )
    logger.info(
        "Transmit service ready: MT=%s MC=%s",
        tx_svc.meshtastic_enabled, tx_svc.meshcore_enabled,
    )
    return tx_svc


def _wire_native_relay(
    coord: PipelineCoordinator, tx_service: TxService | None
) -> None:
    """Hook the native onboard SX1302 path into the relay manager.

    When ``transmit.enabled`` is true the onboard radio is the
    preferred relay backend: it preserves the original sender's
    identity, shares duty-cycle accounting with outbound messaging,
    and removes the need for a second USB-attached node.

    The legacy ``MeshtasticTransmitter`` (USB-companion) wired by
    :class:`PipelineCoordinator._setup_relay_transmitter` is left in
    place; if both backends end up present, the native one wins
    because it is registered second. A future cleanup can drop the
    USB-companion path entirely once hardware-validated.
    """
    if tx_service is None or not tx_service.meshtastic_enabled:
        return
    relay = coord.relay_manager
    if not relay.enabled:
        return

    async def _native_relay(packet):
        from src.models.packet import Protocol
        if packet.protocol != Protocol.MESHTASTIC:
            return
        if not packet.raw_radio_packet:
            return
        result = await tx_service.send_raw_relay(packet.raw_radio_packet)
        if not result.success:
            logger.debug(
                "Native relay TX skipped: %s", result.error,
            )

    relay.set_transmit_function(_native_relay)
    relay.set_local_node_id(f"{tx_service.source_node_id:08x}")
    logger.info(
        "Relay backend: native onboard SX1302 (identity-preserving)"
    )


def _build_nodeinfo_broadcaster(
    config: AppConfig, tx_service: TxService | None
) -> NodeInfoBroadcaster | None:
    """Schedule periodic NodeInfo broadcasts when Meshtastic TX is live.

    Always returns a broadcaster instance when the Meshtastic TX
    backend is available, even if the configured interval is ``0``
    (paused). The pause-aware loop sits idle on its wake event in
    that case and resumes the moment :meth:`set_interval` is called
    with a non-zero value, so the radio tab can hot-reload from
    paused to active without a service restart.

    Returns ``None`` only when transmit is disabled at the config
    level, the TX service is unavailable, or the radio backend
    isn't ready: in those cases there's nothing to broadcast on.
    """
    if tx_service is None or not config.transmit.enabled:
        return None
    if not tx_service.meshtastic_enabled:
        logger.info(
            "NodeInfo broadcaster skipped: Meshtastic TX backend "
            "not available"
        )
        return None

    ni = config.transmit.nodeinfo
    interval_minutes = clamp_interval_minutes(ni.interval_minutes)
    startup_delay = max(0, ni.startup_delay_seconds)
    if interval_minutes == 0:
        logger.info(
            "NodeInfo broadcaster starting paused "
            "(transmit.nodeinfo.interval_minutes=0); save a non-zero "
            "interval on the radio tab to resume."
        )
    return NodeInfoBroadcaster(
        tx_service=tx_service,
        long_name=config.transmit.long_name,
        short_name=config.transmit.short_name,
        startup_delay_seconds=startup_delay,
        interval_seconds=interval_minutes * 60,
    )


RAK2287_TX_GAIN_LUT = [
    {"rf_power": 12, "pa_gain": 0, "pwr_idx": 15},
    {"rf_power": 13, "pa_gain": 0, "pwr_idx": 16},
    {"rf_power": 14, "pa_gain": 0, "pwr_idx": 17},
    {"rf_power": 15, "pa_gain": 0, "pwr_idx": 19},
    {"rf_power": 16, "pa_gain": 0, "pwr_idx": 20},
    {"rf_power": 17, "pa_gain": 0, "pwr_idx": 22},
    {"rf_power": 18, "pa_gain": 1, "pwr_idx": 1},
    {"rf_power": 19, "pa_gain": 1, "pwr_idx": 2},
    {"rf_power": 20, "pa_gain": 1, "pwr_idx": 3},
    {"rf_power": 21, "pa_gain": 1, "pwr_idx": 4},
    {"rf_power": 22, "pa_gain": 1, "pwr_idx": 5},
    {"rf_power": 23, "pa_gain": 1, "pwr_idx": 6},
    {"rf_power": 24, "pa_gain": 1, "pwr_idx": 7},
    {"rf_power": 25, "pa_gain": 1, "pwr_idx": 9},
    {"rf_power": 26, "pa_gain": 1, "pwr_idx": 11},
    {"rf_power": 27, "pa_gain": 1, "pwr_idx": 14},
]


def _inject_tx_gain_into_source(coord: PipelineCoordinator) -> None:
    """Patch the concentrator source startup to include TX gain config.

    lgw_txgain_setconf must be called between lgw_configure and lgw_start.
    Rather than stopping/restarting the concentrator after the capture loop
    is running (which kills RX), we patch the source's start() method to
    inject the TX gain LUT into its normal startup sequence.
    """
    conc_source = _find_concentrator_source(coord)
    if conc_source is None:
        return

    async def _start_with_tx_gain() -> None:
        conc_source._wrapper.load()
        conc_source._wrapper.reset()
        conc_source._wrapper.configure(conc_source._channel_plan)
        conc_source._wrapper.configure_tx_gain(0, RAK2287_TX_GAIN_LUT)
        logger.info(
            "TX gain LUT configured: %d entries on RF chain 0",
            len(RAK2287_TX_GAIN_LUT),
        )
        conc_source._wrapper.start()
        conc_source._wrapper.set_syncword(conc_source._syncword)
        conc_source._running = True
        logger.info(
            "Concentrator started with TX gain (syncword=0x%02X)",
            conc_source._syncword,
        )

    conc_source.start = _start_with_tx_gain


def _find_meshcore_source(coord: PipelineCoordinator):
    """Find the MeshCore USB capture source if it exists."""
    for src in coord.capture_coordinator._sources:
        if src.name == "meshcore_usb":
            return src
    return None


async def _reapply_companion_name(meshcore_tx, config: AppConfig) -> None:
    """Re-apply the configured companion name on every USB connect.

    Mirrors how ``sync_channels`` keeps user-configured channel keys in
    sync across reconnects: when a user has set
    ``meshcore.companion_name`` (via the Configuration -> MeshCore
    card or hand-edited local.yaml), we want a freshly-flashed
    companion or a hot-swap to land on that name without a manual
    re-save.

    Failure is logged but never raises -- the channel sync that ran
    first is more important to the user than the rename, and
    sync_channels has already restored the runtime state we need.
    """
    desired = (config.meshcore.companion_name or "").strip()
    if not desired:
        return

    if not meshcore_tx.connected:
        return

    try:
        result = await meshcore_tx.set_companion_name(desired)
    except Exception:
        logger.exception("companion_name re-apply on connect raised")
        return

    if result.success:
        logger.info("Re-applied companion_name=%r on connect", desired)
    else:
        logger.warning(
            "Failed to re-apply companion_name=%r on connect: %s",
            desired,
            result.error,
        )


def _find_concentrator_source(coord: PipelineCoordinator):
    """Find the concentrator capture source."""
    for src in coord.capture_coordinator._sources:
        if hasattr(src, "_wrapper"):
            return src
    return None


def _get_concentrator_wrapper(coord: PipelineCoordinator):
    """Get the SX1302 wrapper from the concentrator source if running."""
    src = _find_concentrator_source(coord)
    return src._wrapper if src else None


def _build_spectral_scan_service(
    coord: PipelineCoordinator,
    config: AppConfig,
    tracker: NoiseFloorTracker,
) -> SpectralScanService | None:
    """Build the spectral scan service if hardware + config allow.

    Returns None when:
      - The concentrator is not present (e.g. test container)
      - radio.spectral_scan_interval_seconds is 0 (user disabled)
      - The loaded HAL does not expose spectral scan symbols (the
        service itself will detect this and no-op on start, but we
        also early-return to avoid the log noise)
    """
    interval = config.radio.spectral_scan_interval_seconds
    if interval is None or interval <= 0:
        logger.info("Spectral scan disabled via radio.spectral_scan_interval_seconds")
        return None
    wrapper = _get_concentrator_wrapper(coord)
    if wrapper is None:
        return None
    if not wrapper.spectral_scan_supported:
        return None
    freq_mhz = config.radio.frequency_mhz
    if freq_mhz is None:
        logger.warning("Spectral scan: no resolved radio.frequency_mhz; skipping")
        return None
    return SpectralScanService(
        wrapper=wrapper,
        tracker=tracker,
        frequency_hz=int(freq_mhz * 1_000_000),
        bandwidth_khz=config.radio.bandwidth_khz,
        interval_seconds=float(interval),
    )


def _get_channel_plan(config: AppConfig):
    """Build a channel plan for TX frequency/modulation parameters."""
    try:
        from src.hal.concentrator_config import ConcentratorChannelPlan
        return ConcentratorChannelPlan.for_region(config.radio.region)
    except Exception:
        return None


async def _send_meshcore_advert(meshcore_tx, mc_source=None) -> None:
    """Broadcast a name advertisement so other MeshCore nodes see a friendly name."""
    try:
        result = await meshcore_tx.send_advert()
        if result.success:
            logger.info("MeshCore advert sent on startup")
        else:
            logger.warning("MeshCore advert failed: %s", result.error)
    except Exception:
        logger.debug("MeshCore advert failed", exc_info=True)
    try:
        contacts = await meshcore_tx.get_contacts()
        if contacts:
            log_meshcore_contact_peers(contacts)
        else:
            logger.info(
                "MeshCore contacts: 0 peers (companion roster still loading; "
                "will retry in ~20s)",
            )
    except Exception:
        logger.debug("Startup contact fetch failed", exc_info=True)
    if mc_source:
        await mc_source.restart_auto_fetching()


def _setup_message_interception(
    coord: PipelineCoordinator,
    message_repo: MessageRepository,
    config: AppConfig,
    meshcore_tx=None,
    tx_service: TxService | None = None,
) -> None:
    """Register a callback to intercept TEXT messages for storage.

    Filters DMs: only saves messages involving our node_id as normal
    conversations. DMs between other nodes are tagged as 'overheard'.
    MeshCore DMs use destination_id='self' to indicate they're for us.
    """
    from src.api.message_name_resolver import MessageNameResolver
    from src.models.packet import PacketType, Protocol

    name_resolver = MessageNameResolver(coord.node_repo, meshcore_tx)

    our_node_id = config.transmit.node_id
    if our_node_id is None and tx_service is not None:
        our_node_id = tx_service.source_node_id
    our_node_hex = f"{our_node_id:08x}" if our_node_id else ""

    mc_name_cache: dict[str, str] = {}
    mc_pubkey_canon: dict[str, str] = {}

    channel_hash_map: dict[int, int] = {}
    try:
        crypto = coord._crypto
        all_keys = crypto.get_all_keys()
        primary_name = config.meshtastic.primary_channel_name
        if all_keys:
            h = crypto.compute_channel_hash(primary_name, all_keys[0])
            channel_hash_map[h] = 0
        for i, (ch_name, _) in enumerate(
            config.meshtastic.channel_keys.items(), start=1
        ):
            if i < len(all_keys):
                h = crypto.compute_channel_hash(ch_name, all_keys[i])
                channel_hash_map[h] = i
        logger.info("Channel hash map: %s", channel_hash_map)
    except Exception:
        logger.debug("Failed to build channel hash map", exc_info=True)

    async def _refresh_mc_contacts() -> None:
        if not meshcore_tx or not meshcore_tx.connected:
            logger.debug("MC contact refresh skipped: not connected")
            return
        try:
            contacts = await meshcore_tx.get_contacts()
            for c in contacts:
                pk = c.get("public_key", "")
                name = c.get("name", "")
                if not pk:
                    continue
                canonical = pk[:12].lower() if len(pk) >= 12 else pk.lower()
                for prefix_len in (8, 10, 12, 16, len(pk)):
                    prefix = pk[:prefix_len].lower()
                    mc_pubkey_canon[prefix] = canonical
                    if name:
                        mc_name_cache[prefix] = name
            logger.debug(
                "MC contact cache refreshed: %d name, %d pubkey entries",
                len(mc_name_cache), len(mc_pubkey_canon),
            )
        except Exception:
            logger.debug("MC contact cache refresh failed", exc_info=True)

    def _is_hex_only(s: str) -> bool:
        try:
            int(s, 16)
            return len(s) >= 6
        except ValueError:
            return False

    def _resolve_mc_display_name(source: str, payload: dict) -> str:
        src_lower = source.lower()
        for length in (len(src_lower), 12, 8, 16):
            cached = mc_name_cache.get(src_lower[:length], "")
            if cached and not _is_hex_only(cached):
                return cached
        name = payload.get("long_name", "")
        if name and not _is_hex_only(name):
            return name
        return ""

    def _normalize_mc_node_id(source: str) -> str:
        """Map any pubkey prefix to the canonical 12-char lowercase form."""
        src_lower = source.lower()
        for length in (len(src_lower), 12, 8, 16):
            canon = mc_pubkey_canon.get(src_lower[:length], "")
            if canon:
                return canon
        return src_lower

    def on_text_packet(packet: Packet) -> None:
        if packet.packet_type != PacketType.TEXT:
            return
        text = ""
        if packet.decoded_payload:
            text = packet.decoded_payload.get("text", "")
        if not text:
            return

        dest = (packet.destination_id or "").lower()
        source = (packet.source_id or "").lower()
        is_broadcast = dest in ("ffffffff", "ffff", "broadcast") or dest.startswith("channel:")
        is_for_us = (
            (our_node_hex and dest == our_node_hex)
            or dest == "self"
        )

        if is_broadcast:
            if our_node_hex and source == our_node_hex:
                return
            if packet.protocol == Protocol.MESHCORE:
                ch_idx = packet.channel_hash or 0
            else:
                ch_idx = channel_hash_map.get(packet.channel_hash, 0)
            node_id = f"broadcast:{packet.protocol.value}:{ch_idx}"
            direction = "received"
        elif is_for_us:
            node_id = packet.source_id or "unknown"
            direction = "received"
        elif our_node_hex and source == our_node_hex:
            node_id = packet.destination_id or "unknown"
            direction = "sent"
        else:
            node_id = packet.source_id or "unknown"
            direction = "overheard"

        node_name = ""
        if packet.decoded_payload:
            node_name = packet.decoded_payload.get("long_name", "")

        is_mc_dm = (
            packet.protocol == Protocol.MESHCORE
            and direction == "received"
            and not is_broadcast
        )

        rssi = packet.signal.rssi if packet.signal else None
        snr = packet.signal.snr if packet.signal else None

        import asyncio

        async def _save_and_notify() -> None:
            nonlocal node_id, node_name
            if is_mc_dm:
                if meshcore_tx:
                    await _refresh_mc_contacts()
                resolved_name = _resolve_mc_display_name(
                    node_id, packet.decoded_payload or {}
                )
                if resolved_name and not node_name:
                    node_name = resolved_name
                node_id = _normalize_mc_node_id(node_id)
            if (
                packet.protocol == Protocol.MESHTASTIC
                and direction == "received"
            ):
                sender_lookup = (
                    (packet.source_id or "")
                    if is_broadcast
                    else node_id
                )
                node_name = await name_resolver.resolve(
                    sender_lookup,
                    packet.protocol.value,
                    node_name or packet.source_id or "",
                )

            if is_broadcast and packet.protocol == Protocol.MESHCORE:
                node_name = (packet.decoded_payload or {}).get("long_name", "")

            if packet.protocol == Protocol.MESHCORE and not is_broadcast:
                payload_name = (packet.decoded_payload or {}).get("long_name", "")
                if payload_name and not _is_hex_only(payload_name):
                    node_name = payload_name

            if (
                packet.protocol == Protocol.MESHCORE
                and node_name
                and not _is_hex_only(node_name)
            ):
                src = (packet.source_id or "").lower()
                if src and src != node_name.lower():
                    await coord.node_repo._db.execute(
                        "UPDATE nodes SET long_name = ? "
                        "WHERE LOWER(node_id) LIKE ? AND protocol = 'meshcore'",
                        (node_name, src[:8] + "%"),
                    )
                    await coord.node_repo._db.commit()

            if (
                packet.protocol == Protocol.MESHCORE
                and (not node_name or _is_hex_only(node_name))
            ):
                row = await coord.node_repo._db.fetch_one(
                    "SELECT long_name FROM nodes "
                    "WHERE LOWER(node_id) LIKE ? AND protocol = 'meshcore' "
                    "AND long_name IS NOT NULL AND long_name != ''",
                    (node_id[:8] + "%",),
                )
                if row:
                    rn = row["long_name"] or ""
                    if rn and not _is_hex_only(rn):
                        node_name = rn

            if (
                packet.protocol == Protocol.MESHCORE
                and (not node_name or _is_hex_only(node_name))
            ):
                mc_row = await coord.node_repo._db.fetch_one(
                    "SELECT node_id, long_name FROM nodes "
                    "WHERE node_id LIKE 'mc:%' AND protocol = 'meshcore' "
                    "AND node_id NOT IN ('mc:channel')",
                )
                if mc_row:
                    rn = mc_row["long_name"] or mc_row["node_id"][3:]
                    if rn and not _is_hex_only(rn):
                        node_name = rn
                        await coord.node_repo._db.execute(
                            "UPDATE nodes SET long_name = ? WHERE node_id = ?",
                            (rn, node_id),
                        )
                        await coord.node_repo._db.commit()
            row_id, is_dup = await message_repo.save_received(
                text=text,
                node_id=node_id,
                node_name=node_name,
                protocol=packet.protocol.value,
                packet_id=packet.packet_id or "",
                direction=direction,
                rssi=rssi,
                snr=snr,
            )
            if is_dup:
                row = await message_repo._db.fetch_one(
                    "SELECT rx_count, rssi, snr FROM messages WHERE id=?",
                    (row_id,),
                )
                await ws_manager.broadcast("message_updated", {
                    "packet_id": packet.packet_id or "",
                    "node_id": node_id,
                    "rx_count": row["rx_count"] if row else 2,
                    "rssi": round(row["rssi"], 1) if row and row["rssi"] else None,
                    "snr": round(row["snr"], 1) if row and row["snr"] else None,
                })
            else:
                ws_name_lookup = (
                    (packet.source_id or "")
                    if is_broadcast and packet.protocol == Protocol.MESHTASTIC
                    else node_id
                )
                display_name = await name_resolver.resolve(
                    ws_name_lookup,
                    packet.protocol.value,
                    node_name,
                )
                ws_payload = {
                    "text": text,
                    "node_id": node_id,
                    "node_name": display_name,
                    "protocol": packet.protocol.value,
                    "direction": direction,
                    "packet_id": packet.packet_id or "",
                    "source_id": packet.source_id or "",
                    "destination_id": packet.destination_id or "",
                }
                if rssi is not None:
                    ws_payload["rssi"] = round(rssi, 1)
                if snr is not None:
                    ws_payload["snr"] = round(snr, 1)
                await ws_manager.broadcast("message_received", ws_payload)

        try:
            asyncio.get_running_loop().create_task(_save_and_notify())
        except RuntimeError:
            pass

    coord.on_packet(on_text_packet)


def _init_routes(
    coord: PipelineCoordinator,
    config: AppConfig,
    identity: DeviceIdentity,
    auth_subsystem: AuthSubsystem,
    tx_service: TxService | None = None,
    message_repo: MessageRepository | None = None,
) -> None:
    identity_routes.init_routes(identity, auth_subsystem.service)
    network_mapper = NetworkMapper(coord.node_repo)
    signal_analyzer = SignalAnalyzer(coord.packet_repo)
    traffic_monitor = TrafficMonitor(coord.packet_repo)

    nodes.init_routes(
        coord.node_repo,
        network_mapper,
        packet_repo=coord.packet_repo,
        telemetry_repo=coord.telemetry_repo,
    )
    packets.init_routes(coord.packet_repo)
    analytics.init_routes(signal_analyzer, traffic_monitor, coord.packet_repo)
    device.init_routes(identity, ws_manager, coord.relay_manager)
    telemetry.init_routes(coord.telemetry_repo)
    stats_routes.init_routes(
        stats_reporter=coord.stats_reporter,
        signal_analyzer=signal_analyzer,
        traffic_monitor=traffic_monitor,
        network_mapper=network_mapper,
        relay_manager=coord.relay_manager,
        node_repo=coord.node_repo,
        packet_repo=coord.packet_repo,
    )

    meshcore_tx = None
    if tx_service and hasattr(tx_service, '_meshcore_tx'):
        meshcore_tx = tx_service._meshcore_tx

    messages.init_routes(
        tx_service=tx_service,
        message_repo=message_repo or MessageRepository(coord.database),
        node_repo=coord.node_repo,
        meshcore_tx=meshcore_tx,
        config=config,
        packet_repo=coord.packet_repo,
    )

    crypto = coord._crypto if hasattr(coord, "_crypto") else None
    nodeinfo_routes.init_routes(
        config=config,
        nodeinfo_broadcaster=nodeinfo_broadcaster,
    )
    config_routes.init_routes(
        config=config,
        crypto=crypto,
        tx_service=tx_service,
        identity=identity,
    )
    mqtt_config_routes.init_routes(config=config)
    upstream_config_routes.init_routes(config=config)
    device_config_routes.init_routes(config=config, identity=identity)
    gps_status.init_routes(location_source=coord.location_source)
    system_config_routes.init_routes(config=config)
    meshcore_config_routes.init_routes(config=config, tx_service=tx_service)


def _init_dangerous_registry(coord: PipelineCoordinator) -> None:
    """Compose the Settings → Dangerous registry now that the pipeline is live.

    Restart actions don't need pipeline state -- they go through
    ``systemctl`` -- but database / phantom / nodeinfo operations
    have to close over the running coordinator. Doing this from the
    lifespan keeps the wiring honest: by the time these handlers
    fire, every collaborator has been instantiated.
    """
    import asyncio
    loop = asyncio.get_running_loop()

    def _dispatch(coro):
        return asyncio.run_coroutine_threadsafe(coro, loop)

    async def _clear_database_coro() -> int:
        db = coord.database
        removed = 0
        for table in ("packets", "messages", "nodes"):
            try:
                rc = await db.execute(f"DELETE FROM {table}")
                if rc and getattr(rc, "rowcount", 0):
                    removed += int(rc.rowcount)
            except Exception:
                logger.exception("clear_database: failed on table %s", table)
        try:
            await db.commit()
        except Exception:
            pass
        return removed

    async def _wipe_phantoms_coro() -> int:
        return await coord.node_repo.delete_phantom_rows()

    async def _force_nodeinfo_coro() -> bool:
        if nodeinfo_broadcaster is None:
            return False
        try:
            result = await nodeinfo_broadcaster.broadcast_now()
            return bool(result.success)
        except Exception:
            logger.exception("force_nodeinfo: broadcast failed")
            return False

    async def _restart_concentrator_coro() -> bool:
        src = _find_concentrator_source(coord)
        if src is None:
            logger.warning("restart_concentrator: no concentrator capture source")
            return False
        try:
            await src.restart_pipeline()
            return True
        except Exception:
            logger.exception("restart_concentrator: pipeline reload failed")
            return False

    registry = DangerousActionRegistry([
        build_restart_service_action(),
        build_restart_concentrator_action(
            dispatch=_dispatch,
            restart_coro_factory=_restart_concentrator_coro,
        ),
        build_clear_database_action(
            dispatch=_dispatch,
            clear_coro_factory=_clear_database_coro,
        ),
        build_wipe_phantoms_action(
            dispatch=_dispatch,
            wipe_coro_factory=_wipe_phantoms_coro,
        ),
        build_force_nodeinfo_action(
            dispatch=_dispatch,
            broadcast_coro_factory=_force_nodeinfo_coro,
        ),
    ])
    dangerous_routes.init_routes(registry)


async def _gate_ws_or_close(
    websocket: WebSocket, jwt_service: JwtSessionService | None
) -> bool:
    """Authenticate a WS upgrade; return True iff the caller may proceed.

    On rejection: completes the WS handshake with ``accept()`` BEFORE
    closing with the custom 4401 code. This sequencing matters --
    closing pre-accept causes Starlette to fail the upgrade with HTTP
    403, which browsers translate to JS close code ``1006`` (Abnormal
    Closure) instead of the negotiated ``4401``. The dashboard's WS
    client only redirects to ``/login`` on ``4401``, so the pre-accept
    close stranded users in an indefinite reconnect loop. Caught in
    the wild on v0.7.3 (Willard, Discord, 2026-05-13).
    """
    claims = authenticate_websocket(websocket, jwt_service)
    if claims is not None:
        return True
    await websocket.accept()
    await websocket.close(code=WS_AUTH_CLOSE_CODE)
    return False


def _request_has_valid_session(
    request: Request, jwt_service: JwtSessionService | None
) -> bool:
    """Quick cookie-only check used by the dashboard root gate.

    Mirrors ``dependencies._claims_or_none`` but takes the service
    explicitly so the route can run even before ``init_auth`` (e.g.
    in tests that exercise pre-bootstrap states). Cookie-only by
    design: bearer-token clients have no business hitting the SPA
    root, they should call ``/api/...`` directly.
    """
    if jwt_service is None:
        return False
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not token:
        return False
    return jwt_service.verify(token) is not None


def _serve_auth_page(static_dir: Path, filename: str) -> FileResponse:
    """Return one of the two pre-auth HTML pages from frontend/auth/."""
    page = static_dir / "auth" / filename
    if not page.exists():
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="auth page not found")
    return FileResponse(str(page), media_type="text/html")


def _on_packet_received(packet: Packet) -> None:
    import asyncio
    if packet.signal is not None:
        noise_floor_tracker.update(
            rssi_dbm=packet.signal.rssi,
            snr_db=packet.signal.snr,
            bandwidth_khz=packet.signal.bandwidth_khz,
        )
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(ws_manager.broadcast("packet", packet.to_dict()))
    except RuntimeError:
        pass


async def _noise_floor_emitter_loop(
    tracker: NoiseFloorTracker, manager: WebSocketManager,
    interval_seconds: float = 1.0,
) -> None:
    """Broadcast the current noise floor snapshot once per second.

    Runs for the lifetime of the FastAPI app. Cancelled cleanly on
    shutdown via the lifespan context manager.
    """
    import asyncio
    try:
        while True:
            await asyncio.sleep(interval_seconds)
            try:
                await manager.broadcast("noise_floor", tracker.snapshot())
            except Exception:
                # Never let a single broadcast error kill the loop.
                pass
    except asyncio.CancelledError:
        pass
