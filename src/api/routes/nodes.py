from __future__ import annotations

from fastapi import APIRouter, HTTPException

from src.analytics.network_mapper import NetworkMapper
from src.storage.node_repository import NodeRepository

router = APIRouter(prefix="/api/nodes", tags=["nodes"])

_node_repo: NodeRepository | None = None
_network_mapper: NetworkMapper | None = None


def init_routes(
    node_repo: NodeRepository, network_mapper: NetworkMapper
) -> None:
    global _node_repo, _network_mapper
    _node_repo = node_repo
    _network_mapper = network_mapper


@router.get("")
async def list_nodes(limit: int = 200):
    return [n.to_dict() for n in await _node_repo.get_all(limit)]


@router.get("/count")
async def node_count():
    count = await _node_repo.get_count()
    return {"count": count}


@router.get("/map")
async def map_data():
    return await _network_mapper.get_map_data()


@router.get("/summary")
async def network_summary():
    return await _network_mapper.get_network_summary()


@router.get("/{node_id}")
async def get_node(node_id: str):
    node = await _node_repo.get_by_id(node_id)
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")
    return node.to_dict()
