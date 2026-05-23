from __future__ import annotations

from fastapi import APIRouter, HTTPException

from src.analytics.network_mapper import NetworkMapper
from src.storage.node_repository import NodeRepository
from src.storage.packet_repository import PacketRepository
from src.storage.telemetry_repository import TelemetryRepository

router = APIRouter(prefix="/api/nodes", tags=["nodes"])

_node_repo: NodeRepository | None = None
_network_mapper: NetworkMapper | None = None
_packet_repo: PacketRepository | None = None
_telemetry_repo: TelemetryRepository | None = None


def init_routes(
    node_repo: NodeRepository,
    network_mapper: NetworkMapper,
    packet_repo: PacketRepository | None = None,
    telemetry_repo: TelemetryRepository | None = None,
) -> None:
    global _node_repo, _network_mapper, _packet_repo, _telemetry_repo
    _node_repo = node_repo
    _network_mapper = network_mapper
    _packet_repo = packet_repo
    _telemetry_repo = telemetry_repo


@router.get("")
async def list_nodes(limit: int = 500, enrich: bool = True):
    if enrich:
        return await _node_repo.get_all_with_signal(limit)
    return [n.to_dict() for n in await _node_repo.get_all(limit)]


@router.get("/count")
async def node_count():
    count = await _node_repo.get_count()
    active = await _node_repo.get_active_count()
    return {"count": count, "active": active}


@router.get("/map")
async def map_data():
    return await _network_mapper.get_map_data()


@router.get("/summary")
async def network_summary():
    return await _network_mapper.get_network_summary()


@router.get("/{node_id}/metrics_history")
async def metrics_history(
    node_id: str,
    limit: int = 300,
    hours: float | None = 168,
):
    """Telemetry rows + RSSI samples for node drawer time-series charts."""
    if _packet_repo is None or _telemetry_repo is None:
        raise HTTPException(status_code=503, detail="Metrics not available")

    node = await _node_repo.get_by_id(node_id)
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")

    telemetry = await _telemetry_repo.get_history(node_id, limit, hours)
    signal = await _packet_repo.get_signal_history(node_id, limit, hours)
    return {
        "node_id": node_id,
        "telemetry": [t.to_dict() for t in telemetry],
        "signal": signal,
    }


@router.get("/{node_id}")
async def get_node(node_id: str):
    node = await _node_repo.get_by_id(node_id)
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")
    return node.to_dict()
