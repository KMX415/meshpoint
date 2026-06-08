"""Webhook status and test endpoints for the dashboard (PR 11)."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from src.webhook.engine import WebhookEngine

router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])

_engine: WebhookEngine | None = None


def init_routes(engine: WebhookEngine | None) -> None:
    global _engine
    _engine = engine


@router.get("/status")
async def webhook_status():
    """Active rules, last-fired timestamps, and engine state (no secrets)."""
    if _engine is None:
        return {
            "enabled": False,
            "engine_running": False,
            "rules": [],
        }
    return _engine.get_status()


@router.post("/test/{rule_name}")
async def webhook_test(rule_name: str):
    """Send a dummy POST to verify the rule URL from the Pi."""
    if _engine is None:
        raise HTTPException(status_code=503, detail="webhook engine not ready")
    try:
        return await _engine.fire_test(rule_name)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
