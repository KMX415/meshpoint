"""HTTP surface for Settings → Dangerous actions.

Two endpoints, both admin-only and audited:

* ``GET  /api/dangerous/actions``  -- enumerate actions for the
  picker; the frontend renders one card per entry with the
  confirmation copy returned here.
* ``POST /api/dangerous/invoke``   -- run an action by id and
  return its structured result.

Every successful or failing invocation goes to the audit log via
``timed_action`` so the operator can see exactly when each
destructive action was triggered (and which user pressed the
button).
"""

from __future__ import annotations

import logging

from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from src.api.audit import AuditLogWriter
from src.api.audit.dependencies import get_audit_writer
from src.api.auth.dependencies import require_admin
from src.api.auth.jwt_session import SessionClaims
from src.api.dangerous.actions import DangerousActionRegistry

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/dangerous", tags=["dangerous"])

_registry: DangerousActionRegistry | None = None


def init_routes(registry: DangerousActionRegistry) -> None:
    global _registry
    _registry = registry


def reset_routes() -> None:
    global _registry
    _registry = None


def _require_registry() -> DangerousActionRegistry:
    if _registry is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="dangerous registry not initialized",
        )
    return _registry


class InvokeRequest(BaseModel):
    action_id: str = Field(..., min_length=1, max_length=64)


@router.get("/actions")
async def list_actions(
    _claims: SessionClaims = Depends(require_admin),
) -> dict:
    registry = _require_registry()
    return {"actions": registry.to_payload()}


@router.post("/invoke")
async def invoke_action(
    payload: InvokeRequest,
    claims: SessionClaims = Depends(require_admin),
    audit: AuditLogWriter = Depends(get_audit_writer),
) -> dict:
    registry = _require_registry()
    action = registry.find(payload.action_id)
    if action is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="unknown_action",
        )
    with audit.timed_action(
        user=claims.subject,
        action=f"dangerous.{action.id}",
        params={"label": action.label},
    ) as ctx:
        result = registry.invoke(action.id)
        ctx.params["success"] = result.success
        if not result.success:
            ctx.set_result("error")
            ctx.params["message"] = result.message
    return asdict(result)
