"""REST endpoints for position broadcast configuration."""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from src.api.auth.dependencies import require_admin
from src.api.auth.jwt_session import SessionClaims
from src.api.routes.broadcast_status import build_broadcast_status
from src.config import AppConfig, save_section_to_yaml

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/config/position", tags=["config"])

_config: AppConfig | None = None
_position_broadcaster = None


def init_routes(
    config: AppConfig,
    position_broadcaster=None,
) -> None:
    global _config, _position_broadcaster
    _config = config
    _position_broadcaster = position_broadcaster


def build_position_status(pos) -> dict:
    return build_broadcast_status(_position_broadcaster, pos)


class PositionBroadcastUpdate(BaseModel):
    interval_minutes: Optional[int] = None
    startup_delay_seconds: Optional[int] = None


@router.put("")
async def update_position_broadcast(
    req: PositionBroadcastUpdate,
    _claims: SessionClaims = Depends(require_admin),
):
    if _config is None:
        raise HTTPException(503, "Config not loaded")

    pos = _config.transmit.position
    updates: dict = {}
    interval_changed = False
    startup_delay_changed = False

    if req.interval_minutes is not None:
        if req.interval_minutes != 0 and not 5 <= req.interval_minutes <= 1440:
            raise HTTPException(
                400,
                "interval_minutes must be 0 (disabled) or 5-1440 "
                "(5 min to 24 hr)",
            )
        pos.interval_minutes = req.interval_minutes
        updates["interval_minutes"] = req.interval_minutes
        interval_changed = True
    if req.startup_delay_seconds is not None:
        if not 0 <= req.startup_delay_seconds <= 3600:
            raise HTTPException(
                400, "startup_delay_seconds must be 0-3600"
            )
        pos.startup_delay_seconds = req.startup_delay_seconds
        updates["startup_delay_seconds"] = req.startup_delay_seconds
        startup_delay_changed = True

    if updates:
        full_position = {
            "interval_minutes": pos.interval_minutes,
            "startup_delay_seconds": pos.startup_delay_seconds,
            "coordinate_source": pos.coordinate_source,
            "location_precision": pos.location_precision,
        }
        try:
            save_section_to_yaml(
                "transmit", {"position": full_position}
            )
        except PermissionError as exc:
            raise HTTPException(403, str(exc)) from exc

    interval_hot_reloaded = False
    if (
        interval_changed
        and _position_broadcaster is not None
        and _position_broadcaster.is_running
    ):
        _position_broadcaster.set_interval(req.interval_minutes)
        interval_hot_reloaded = True

    restart_required = bool(updates) and (
        startup_delay_changed
        or (interval_changed and not interval_hot_reloaded)
    )

    return {
        "saved": True,
        "restart_required": restart_required,
        "interval_hot_reloaded": interval_hot_reloaded,
        "updates": updates,
    }
