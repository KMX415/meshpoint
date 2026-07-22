"""REST endpoints for NodeInfo broadcast configuration and control.

Mounted under ``/api/config/nodeinfo*``. Three concerns:

- :func:`build_nodeinfo_status` builds the live block consumed by
  :mod:`config_routes` ``GET /api/config`` so the radio tab countdown
  card has both persisted config and live broadcaster telemetry.
- :func:`update_nodeinfo` writes the interval to ``local.yaml`` and
  hot-reloads the running broadcaster so changes take effect
  immediately without a service restart.
- :func:`send_nodeinfo_now` triggers the "Send Now" button on the
  radio tab.

Split out of ``config_routes.py`` to keep that file under the 500-line
cap and because the NodeInfo broadcast interval is its own UX surface
in v0.7.1.
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from src.api.auth.dependencies import require_admin
from src.api.auth.jwt_session import SessionClaims
from src.config import AppConfig, save_section_to_yaml

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/config/nodeinfo", tags=["config"])

_config: AppConfig | None = None
_nodeinfo_broadcaster = None


def init_routes(
    config: AppConfig,
    nodeinfo_broadcaster=None,
) -> None:
    global _config, _nodeinfo_broadcaster
    _config = config
    _nodeinfo_broadcaster = nodeinfo_broadcaster


def build_nodeinfo_status(ni) -> dict:
    """Build the NodeInfo block for ``GET /api/config``.

    Includes both the persisted config (interval, startup delay) and
    live broadcaster telemetry (running flag, last_sent_at, next_due_at)
    that the Radio tab uses to render the countdown card.
    Timestamps are emitted as UTC ISO-8601 strings so the JS Date
    constructor parses them losslessly.
    """
    last_sent = None
    next_due = None
    running = False
    if _nodeinfo_broadcaster is not None:
        running = _nodeinfo_broadcaster.is_running
        if _nodeinfo_broadcaster.last_sent_at is not None:
            last_sent = _nodeinfo_broadcaster.last_sent_at.isoformat()
        if _nodeinfo_broadcaster.next_due_at is not None:
            next_due = _nodeinfo_broadcaster.next_due_at.isoformat()
    return {
        "interval_minutes": ni.interval_minutes,
        "startup_delay_seconds": ni.startup_delay_seconds,
        "running": running,
        "last_sent_at": last_sent,
        "next_due_at": next_due,
    }


class NodeInfoUpdate(BaseModel):
    interval_minutes: Optional[int] = None
    startup_delay_seconds: Optional[int] = None


@router.put("")
async def update_nodeinfo(
    req: NodeInfoUpdate,
    _claims: SessionClaims = Depends(require_admin),
):
    """Update NodeInfo broadcast settings.

    ``interval_minutes`` hot-reloads the running broadcaster: the new
    interval takes effect within milliseconds and the next broadcast
    fires at ``last_sent_at + new_interval`` (or right away if that's
    already past). Set to ``0`` to pause; restore to a non-zero value
    to resume. No service restart needed when the broadcaster is
    already running.

    ``startup_delay_seconds`` only applies at service start, so changes
    require a restart to take effect on the next boot.

    If the broadcaster isn't running at all (e.g., TX disabled at
    boot, radio backend not ready), a restart is required to start
    it; ``interval_hot_reloaded`` will be ``false`` in that case.
    """
    if _config is None:
        raise HTTPException(503, "Config not loaded")

    ni = _config.transmit.nodeinfo
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
        ni.interval_minutes = req.interval_minutes
        updates["interval_minutes"] = req.interval_minutes
        interval_changed = True
    if req.startup_delay_seconds is not None:
        if not 0 <= req.startup_delay_seconds <= 3600:
            raise HTTPException(
                400, "startup_delay_seconds must be 0-3600"
            )
        ni.startup_delay_seconds = req.startup_delay_seconds
        updates["startup_delay_seconds"] = req.startup_delay_seconds
        startup_delay_changed = True

    if updates:
        full_nodeinfo = {
            "interval_minutes": ni.interval_minutes,
            "startup_delay_seconds": ni.startup_delay_seconds,
        }
        try:
            save_section_to_yaml(
                "transmit", {"nodeinfo": full_nodeinfo}
            )
        except PermissionError as exc:
            raise HTTPException(403, str(exc))

    interval_hot_reloaded = False
    if (
        interval_changed
        and _nodeinfo_broadcaster is not None
        and _nodeinfo_broadcaster.is_running
    ):
        _nodeinfo_broadcaster.set_interval(req.interval_minutes)
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


@router.post("/send")
async def send_nodeinfo_now(
    _claims: SessionClaims = Depends(require_admin),
):
    """Trigger an immediate NodeInfo broadcast (the 'Send Now' button).

    Returns 503 when the broadcaster isn't running, which can happen
    if TX is disabled or the Meshtastic radio backend isn't ready.
    On success, the broadcaster's ``last_sent_at`` is re-anchored so
    the dashboard countdown immediately reflects the new schedule.
    """
    if _nodeinfo_broadcaster is None:
        raise HTTPException(
            503,
            "NodeInfo broadcaster not active "
            "(TX disabled or radio backend not ready).",
        )
    result = await _nodeinfo_broadcaster.broadcast_now()
    return {
        "success": result.success,
        "packet_id": result.packet_id,
        "airtime_ms": result.airtime_ms,
        "error": result.error,
    }
