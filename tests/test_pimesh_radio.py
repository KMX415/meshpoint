from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from meshtastic.protobuf import config_pb2, module_config_pb2

from src.capture.meshtasticd_control import read_radio_state_from_iface
from src.cli.meshcore_radio_config import REGION_PRESETS, RadioStatus
from src.radio.openhop_control import apply_radio
from src.transmit.pimesh_position import PimeshPositionTransmitter
from src.transmit.tx_service import SendResult


@pytest.mark.asyncio
async def test_host_radio_rejects_out_of_band_before_network_call():
    with (
        patch("src.radio.openhop_control.read_json", return_value={"region": "US"}),
        patch("src.radio.openhop_control._post") as post,
    ):
        with pytest.raises(ValueError, match="outside"):
            await apply_radio(AsyncMock(), REGION_PRESETS["EU_UK_NARROW"])
        post.assert_not_called()


@pytest.mark.asyncio
async def test_host_radio_requires_fresh_matching_hardware_readback():
    mc = SimpleNamespace(
        refresh_radio_info=AsyncMock(
            return_value=RadioStatus(
                frequency_mhz=915.8,
                bandwidth_khz=250,
                spreading_factor=10,
                coding_rate=5,
            )
        )
    )
    with (
        patch("src.radio.openhop_control.read_json", return_value={"region": "US"}),
        patch("pathlib.Path.read_text", return_value='{"password":"test-only"}'),
        patch(
            "src.radio.openhop_control._post",
            side_effect=[{"token": "test-only"}, {"data": {"live_update": True}}],
        ),
        pytest.raises(RuntimeError, match="readback"),
    ):
        await apply_radio(mc, REGION_PRESETS["USA_CANADA"])


@pytest.mark.asyncio
async def test_position_never_advertises_stale_coordinates_after_failure():
    mc = SimpleNamespace(
        connected=True,
        set_coordinates=AsyncMock(
            return_value=SendResult(success=False, protocol="meshcore", error="timeout")
        ),
        send_advert=AsyncMock(),
    )
    adapter = PimeshPositionTransmitter(SimpleNamespace(_meshcore_tx=mc), "meshcore")
    result = await adapter.send_position(38, -98, 100)
    assert not result.success
    mc.send_advert.assert_not_called()


@pytest.mark.asyncio
async def test_native_position_keeps_radio_packet_id():
    source = SimpleNamespace(
        request_send_position=MagicMock(return_value=(True, {"packet_id": "12345678"}))
    )
    adapter = PimeshPositionTransmitter(
        SimpleNamespace(
            _meshtasticd_tx=SimpleNamespace(connected=True, _source=source)
        ),
        "meshtastic",
    )
    result = await adapter.send_position(38, -98)
    assert result.success and result.packet_id == "12345678"


def test_real_protobuf_radio_snapshot_uses_owner_and_active_preset():
    cfg = config_pb2.Config()
    cfg.lora.region = config_pb2.Config.LoRaConfig.US
    cfg.lora.use_preset = True
    cfg.lora.modem_preset = config_pb2.Config.LoRaConfig.SHORT_FAST
    iface = SimpleNamespace(
        localNode=SimpleNamespace(
            nodeNum=123,
            localConfig=cfg,
            moduleConfig=module_config_pb2.ModuleConfig(),
            getChannelByChannelIndex=lambda _: None,
        ),
        nodesByNum={123: {"user": {"longName": "Saved owner", "shortName": "SAVE"}}},
    )
    state = read_radio_state_from_iface(iface)
    assert state.long_name == "Saved owner"
    assert state.spreading_factor == 7
    assert state.bandwidth_khz == 250
    assert 902 < state.frequency_mhz < 928


@pytest.mark.asyncio
async def test_meshcore_position_scheduler_accepts_companion_result():
    from src.transmit.meshcore_tx_client import SendResult as CompanionResult
    from src.transmit.position_broadcaster import PositionBroadcaster

    mc = SimpleNamespace(
        connected=True,
        set_coordinates=AsyncMock(return_value=CompanionResult(success=True)),
        send_advert=AsyncMock(return_value=CompanionResult(success=True)),
    )
    adapter = PimeshPositionTransmitter(SimpleNamespace(_meshcore_tx=mc), "meshcore")
    broadcaster = PositionBroadcaster(adapter, coords_provider=lambda: (38, -98, None))
    await broadcaster._broadcast_once()
    assert broadcaster.last_sent_at is not None


@pytest.mark.asyncio
async def test_meshcore_tx_disable_blocks_all_application_rf_commands():
    from src.transmit.meshcore_tx_client import MeshCoreTxClient

    client = MeshCoreTxClient()
    client.tx_enabled_provider = lambda: False
    client._run_tx_command = AsyncMock()
    assert not (await client.send_channel_message(0, "test")).success
    assert not (await client.send_direct_message("contact", "test")).success
    assert not (await client.send_advert()).success
    client._run_tx_command.assert_not_called()


@pytest.mark.asyncio
async def test_background_start_is_not_connected_until_handshake():
    from src.capture.meshtasticd_bridge_source import MeshtasticdBridgeSource

    source = MeshtasticdBridgeSource(connect_in_background=True)
    source._worker = MagicMock()
    source._worker.is_alive.return_value = True
    await source.start()
    assert not source.is_running


def test_late_meshtastic_identity_filters_our_own_broadcast():
    from src.api.server import _setup_message_interception
    from src.config import AppConfig
    from src.models.packet import PacketType, Protocol

    cfg = AppConfig()
    cfg.device.platform = "node"
    source = SimpleNamespace(local_node_id_hex=None)
    coord = MagicMock()
    with patch("src.api.server._find_meshtasticd_source", return_value=source):
        _setup_message_interception(coord, MagicMock(), cfg)
    callback = coord.on_packet.call_args.args[0]
    source.local_node_id_hex = "12345678"
    packet = SimpleNamespace(
        packet_type=PacketType.TEXT,
        protocol=Protocol.MESHTASTIC,
        decoded_payload={"text": "test"},
        destination_id="ffffffff",
        source_id="12345678",
    )
    # A background handshake must not raise or save our own echo as incoming.
    with patch("asyncio.get_running_loop") as loop:
        callback(packet)
        loop.assert_not_called()


def test_viewer_cannot_switch_radio():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from src.api.auth.jwt_session import JwtSessionService
    from src.api.routes.pimesh_routes import build_router
    from src.config import AppConfig

    app = FastAPI()
    app.include_router(build_router(AppConfig()))
    jwt_service = JwtSessionService("test-only-secret-at-least-32-bytes", 60, 1)
    with (
        patch("src.api.auth.dependencies._jwt_service", jwt_service),
        TestClient(app) as client,
    ):
        result = client.post(
            "/api/pimesh/protocol",
            json={"protocol": "meshcore"},
            headers={"Authorization": "Bearer " + jwt_service.issue("guest", "viewer")},
        )
        assert result.status_code == 403
