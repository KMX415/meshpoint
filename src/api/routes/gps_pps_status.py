"""Read-only HAL GPS/PPS sync status from the concentrator wrapper."""

from __future__ import annotations

import logging
from typing import Callable, Optional

from fastapi import APIRouter

from src.hal.sx1302_wrapper import SX1302Wrapper

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/device", tags=["device"])

_get_wrapper: Optional[Callable[[], Optional[SX1302Wrapper]]] = None


def init_routes(
    get_wrapper: Callable[[], Optional[SX1302Wrapper]],
) -> None:
    global _get_wrapper
    _get_wrapper = get_wrapper


def reset_routes() -> None:
    global _get_wrapper
    _get_wrapper = None


@router.get("/gps-pps-status")
async def gps_pps_status() -> dict:
    """Return HAL PPS sync state (separate from ``/api/device/gps-status``)."""
    if _get_wrapper is None:
        return _idle_payload(error="routes not initialized")

    wrapper = _get_wrapper()
    if wrapper is None:
        return _idle_payload(error="concentrator capture source not running")

    gps = wrapper.gps_pps
    if gps is None:
        return _idle_payload()

    return gps.get_status().to_dict()


def _idle_payload(error: Optional[str] = None) -> dict:
    return {
        "enabled": False,
        "available": False,
        "tty_path": "",
        "gps_family": "",
        "sync_count": 0,
        "last_sync_ok": False,
        "last_error": error,
        "xtal_err": None,
        "reference_count_us": None,
    }
