"""Read-only API for undecodable RF frames logged by the pipeline."""
from __future__ import annotations

import csv
import io
from datetime import datetime, timezone

from fastapi import APIRouter, Query
from fastapi.responses import PlainTextResponse

from src.storage.stray_frame_repository import StrayFrameRepository

router = APIRouter(prefix="/api/stray_frames", tags=["stray_frames"])

_repo: StrayFrameRepository | None = None


def init_routes(repo: StrayFrameRepository) -> None:
    global _repo
    _repo = repo


@router.get("")
async def list_stray_frames(
    limit: int = Query(200, ge=1, le=2000),
    hours: float | None = Query(24, ge=1, le=720),
    min_rssi: float | None = Query(None, ge=-150, le=0),
    format: str | None = Query(None, alias="format"),
):
    frames = await _repo.list_recent(
        limit=limit, hours=hours, min_rssi=min_rssi,
    )
    if format == "csv":
        return _as_csv(frames)
    total = await _repo.get_count()
    return {
        "frames": [f.to_dict() for f in frames],
        "count": len(frames),
        "total_stored": total,
        "window_hours": hours,
    }


def _as_csv(frames) -> PlainTextResponse:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow([
        "id", "timestamp", "frame_size", "channel_hash",
        "frequency_mhz", "spreading_factor", "bandwidth_khz",
        "rssi", "snr", "capture_source",
    ])
    for frame in frames:
        d = frame.to_dict()
        writer.writerow([
            d["id"], d["timestamp"], d["frame_size"], d["channel_hash"],
            d["frequency_mhz"], d["spreading_factor"], d["bandwidth_khz"],
            d["rssi"], d["snr"], d["capture_source"],
        ])
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    headers = {
        "Content-Disposition": f'attachment; filename="stray_frames_{stamp}.csv"',
    }
    return PlainTextResponse(
        buffer.getvalue(),
        media_type="text/csv",
        headers=headers,
    )
