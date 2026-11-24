"""PiMesh behavior controls validate, isolate protocols, and verify device responses."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from meshtastic.protobuf import admin_pb2, config_pb2

from src.api.auth.dependencies import require_admin, require_auth
from src.api.routes.pimesh_routes import build_router
from src.capture.meshtasticd_device import read_device, validate_device, write_device
from src.radio import openhop_control


def fake_node():
    actual = config_pb2.Config.DeviceConfig(role=0, node_info_broadcast_secs=1234)
    node = MagicMock()
    node.localConfig = SimpleNamespace(device=config_pb2.Config.DeviceConfig())
    node.iface.responseHandlers = {}

    def send(request, **kwargs):
        if request.HasField("set_config"):
            actual.CopyFrom(request.set_config.device)
        else:
            reply = admin_pb2.AdminMessage()
            reply.get_config_response.device.CopyFrom(actual)
            kwargs["onResponse"]({"decoded": {"admin": {"raw": reply}}})
        return SimpleNamespace(id=5)

    node._sendAdmin.side_effect = send
    return node, actual


def test_device_write_preserves_unrelated_fields_and_reads_twice():
    node, actual = fake_node()
    node.localConfig.device.role = 99  # A stale cache cannot confirm this change.
    result = write_device(node, "CLIENT_MUTE", "LOCAL_ONLY")
    assert result["role"] == "CLIENT_MUTE"
    assert result["rebroadcast_mode"] == "LOCAL_ONLY"
    assert actual.node_info_broadcast_secs == 1234
    assert node.localConfig.device.role == actual.role
    assert node._sendAdmin.call_count == 3


def test_device_write_rejected_or_ignored_is_not_confirmed():
    node, _ = fake_node()
    send = node._sendAdmin.side_effect
    node._sendAdmin.side_effect = lambda request, **kw: (
        None if request.HasField("set_config") else send(request, **kw))
    with pytest.raises(RuntimeError, match="differs"):
        write_device(node, "CLIENT_MUTE", "ALL")


def test_device_read_rejects_nak_without_using_cache():
    node = MagicMock()
    node._sendAdmin.side_effect = lambda request, **kw: kw["onResponse"]({"decoded": {"routing": {}}})
    with pytest.raises(RuntimeError, match="readback unavailable"):
        read_device(node)


@pytest.mark.parametrize("role,mode", [("ROUTER_CLIENT", "ALL"), ("CLIENT", "NONE"), ("CLIENT", "ALL_SKIP_DECODING")])
def test_invalid_roles_never_touch_device(role, mode):
    node = MagicMock()
    with pytest.raises(ValueError):
        write_device(node, role, mode)
    node._sendAdmin.assert_not_called()


def test_repeater_allows_skip_decoding():
    validate_device("REPEATER", "ALL_SKIP_DECODING")


@pytest.mark.asyncio
async def test_openhop_requires_persistence_and_matching_readback():
    with patch.object(openhop_control, "_login", AsyncMock(return_value="private")), patch.object(
        openhop_control, "_post", return_value={"success": True, "persisted": False}
    ), patch.object(openhop_control, "_read_mode") as read:
        with pytest.raises(RuntimeError, match="persistence"):
            await openhop_control.apply_mode("forward")
        read.assert_not_called()
    with patch.object(openhop_control, "_login", AsyncMock(return_value="private")), patch.object(
        openhop_control, "_post", return_value={"success": True, "persisted": True}
    ), patch.object(openhop_control, "_read_mode", return_value={"mode": "monitor"}):
        with pytest.raises(RuntimeError, match="readback"):
            await openhop_control.apply_mode("forward")


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(build_router(SimpleNamespace(device=SimpleNamespace(radio_hat="pimesh-v2"))))
    app.dependency_overrides[require_auth] = lambda: None
    app.dependency_overrides[require_admin] = lambda: None
    with TestClient(app) as client:
        yield client


def state(path):
    return {"active": "meshcore", "phase": "ready", "operation_id": "a", "ready": True,
            "protocol": "meshcore", "updated_at": __import__("time").time()}


def test_non_pimesh_behavior_hidden(client):
    with patch("src.api.routes.pimesh_routes.provisioned", return_value=False):
        assert client.get("/api/pimesh/behavior?protocol=meshcore").status_code == 404
        assert client.put("/api/pimesh/behavior", json={"protocol": "meshcore", "mode": "forward"}).status_code == 404


def test_stale_protocol_and_wrong_fields_never_change_backend(client):
    with patch("src.api.routes.pimesh_routes.provisioned", return_value=True), patch(
        "src.api.routes.pimesh_routes.read_json", side_effect=state
    ), patch.object(openhop_control, "apply_mode", AsyncMock()) as apply:
        assert client.put("/api/pimesh/behavior", json={"protocol": "meshtastic", "role": "CLIENT", "rebroadcast_mode": "ALL"}).status_code == 409
        assert client.put("/api/pimesh/behavior", json={"protocol": "meshcore", "mode": "forward", "role": "CLIENT"}).status_code == 422
        apply.assert_not_called()


def test_backend_failure_hides_private_details(client):
    with patch("src.api.routes.pimesh_routes.provisioned", return_value=True), patch(
        "src.api.routes.pimesh_routes.read_json", side_effect=state
    ), patch.object(openhop_control, "apply_mode", AsyncMock(side_effect=RuntimeError("private-password"))):
        response = client.put("/api/pimesh/behavior", json={"protocol": "meshcore", "mode": "forward"})
        assert response.status_code == 503
        assert "private-password" not in response.text


def test_behavior_write_requires_admin(client):
    client.app.dependency_overrides.pop(require_admin)
    assert client.put("/api/pimesh/behavior", json={"protocol": "meshcore", "mode": "forward"}).status_code == 401
