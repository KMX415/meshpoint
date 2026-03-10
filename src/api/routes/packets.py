from __future__ import annotations

from fastapi import APIRouter

from src.storage.packet_repository import PacketRepository

router = APIRouter(prefix="/api/packets", tags=["packets"])

_packet_repo: PacketRepository | None = None


def init_routes(packet_repo: PacketRepository) -> None:
    global _packet_repo
    _packet_repo = packet_repo


@router.get("")
async def list_packets(limit: int = 100):
    packets = await _packet_repo.get_recent(limit)
    return [p.to_dict() for p in packets]


@router.get("/count")
async def packet_count():
    count = await _packet_repo.get_count()
    return {"count": count}


@router.get("/protocols")
async def protocol_distribution():
    return await _packet_repo.get_protocol_distribution()


@router.get("/types")
async def type_distribution():
    return await _packet_repo.get_type_distribution()


@router.get("/by-source/{source_id}")
async def packets_by_source(source_id: str, limit: int = 50):
    packets = await _packet_repo.get_by_source(source_id, limit)
    return [p.to_dict() for p in packets]
