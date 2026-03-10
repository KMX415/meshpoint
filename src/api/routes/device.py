from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter

from src.api.websocket_manager import WebSocketManager
from src.models.device_identity import DeviceIdentity
from src.relay.relay_manager import RelayManager
from src.version import __version__

router = APIRouter(prefix="/api/device", tags=["device"])

_identity: DeviceIdentity | None = None
_ws_manager: WebSocketManager | None = None
_relay_manager: RelayManager | None = None
_start_time: datetime = datetime.now(timezone.utc)


def init_routes(
    identity: DeviceIdentity,
    ws_manager: WebSocketManager,
    relay_manager: RelayManager,
) -> None:
    global _identity, _ws_manager, _relay_manager, _start_time
    _identity = identity
    _ws_manager = ws_manager
    _relay_manager = relay_manager
    _start_time = datetime.now(timezone.utc)


@router.get("")
async def device_info():
    return _identity.to_dict()


@router.get("/status")
async def device_status():
    uptime = (datetime.now(timezone.utc) - _start_time).total_seconds()
    relay_stats = _relay_manager.get_stats() if _relay_manager else {}
    return {
        "status": "running",
        "uptime_seconds": int(uptime),
        "websocket_clients": _ws_manager.client_count,
        "device_id": _identity.device_id,
        "firmware_version": __version__,
        "relay": relay_stats,
    }
