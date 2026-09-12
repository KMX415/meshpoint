"""Opt-in anonymous summaries. No sessions, private payloads, or dashboard socket."""

from __future__ import annotations

import asyncio
import time

from fastapi import APIRouter, HTTPException, Response

from src.api.auth.auth_service import AuthService
from src.api.routes import stats_routes
from src.config import AppConfig

PUBLIC_PAGES = ("dashboard", "stats", "radio")


def available_pages(service: AuthService) -> list[str]:
    cfg = service.config
    if not service.is_setup_complete() or not cfg.public_view_enabled:
        return []
    return [page for page in PUBLIC_PAGES if page in cfg.public_view_pages]


def build_router(config: AppConfig, service: AuthService) -> APIRouter:
    router = APIRouter(prefix="/api/public/view", tags=["public-view"])
    cache: dict[str, tuple[float, dict]] = {}
    lock = asyncio.Lock()

    def require_page(page: str | None = None) -> list[str]:
        pages = available_pages(service)
        if not pages or (page is not None and page not in pages):
            raise HTTPException(404, "Public page unavailable")
        return pages

    @router.get("")
    async def public_index(response: Response):
        pages = require_page()
        response.headers["Cache-Control"] = "no-store"
        return {"pages": pages}

    @router.get("/{page}")
    async def public_page(page: str, response: Response):
        require_page(page)
        response.headers["Cache-Control"] = "no-store"
        async with lock:
            require_page(page)
            cached = cache.get(page)
            if cached and time.monotonic() - cached[0] < 10:
                return cached[1]
            if page == "radio":
                radio = config.radio
                result = {
                    "region": radio.region,
                    "frequency_mhz": radio.frequency_mhz,
                    "bandwidth_khz": radio.bandwidth_khz,
                    "spreading_factor": radio.spreading_factor,
                }
            else:
                result = await stats_routes.public_snapshot(page)
            # Access may have been revoked while the database query was running.
            require_page(page)
            cache[page] = (time.monotonic(), result)
            return result

    return router
