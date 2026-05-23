from __future__ import annotations

from fastapi import APIRouter, HTTPException

from src.storage.telemetry_repository import TelemetryRepository

router = APIRouter(prefix="/api/telemetry", tags=["telemetry"])

_telemetry_repo: TelemetryRepository | None = None


def init_routes(telemetry_repo: TelemetryRepository) -> None:
    global _telemetry_repo
    _telemetry_repo = telemetry_repo


@router.get("/{node_id}")
async def latest_telemetry(node_id: str):
    telemetry = await _telemetry_repo.get_latest_for_node(node_id)
    if not telemetry:
        raise HTTPException(status_code=404, detail="No telemetry for node")
    return telemetry.to_dict()


@router.get("/{node_id}/history")
async def telemetry_history(
    node_id: str, limit: int = 300, hours: float | None = None
):
    records = await _telemetry_repo.get_history(node_id, limit, hours)
    return [t.to_dict() for t in records]
