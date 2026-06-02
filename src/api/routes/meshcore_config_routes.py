"""REST endpoints for MeshCore companion configuration.

Mounted under ``/api/config/meshcore/*``. Today this module owns the
companion-name save path (renames the USB companion via
``MeshCoreTxClient.set_companion_name``); future MeshCore-only config
surfaces (``set_coords``, ``set_tx_power``) will land here too rather
than bloating ``config_routes.py`` further.

Split out of ``config_routes.py`` because that file is already at the
500-line cap, and because companion-only operations don't share state
with the Meshtastic-side radio / channel / identity routes.
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from src.config import AppConfig, save_section_to_yaml

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/config/meshcore", tags=["config", "meshcore"])

_config: AppConfig | None = None
_tx_service = None


def init_routes(config: AppConfig, tx_service=None) -> None:
    """Wire module-level state at app startup.

    ``tx_service`` is the same TxService instance used by the
    Meshtastic-side config routes; we reach through its ``_meshcore_tx``
    attribute so we share one companion handle across the whole API
    rather than opening a second connection.
    """
    global _config, _tx_service
    _config = config
    _tx_service = tx_service


def _resolve_meshcore_tx():
    """Return the live :class:`MeshCoreTxClient` or ``None`` if absent.

    ``getattr`` is intentional: in test fixtures or when MeshCore TX is
    disabled in config, ``_meshcore_tx`` may not exist on the
    TxService.
    """
    if _tx_service is None:
        return None
    return getattr(_tx_service, "_meshcore_tx", None)


class CompanionNameUpdate(BaseModel):
    name: str


@router.put("/companion-name")
async def update_companion_name(req: CompanionNameUpdate) -> dict:
    """Rename the USB companion (CMD_SET_ADVERT_NAME).

    Validation lives in :meth:`MeshCoreTxClient.set_companion_name`
    (single source of truth shared with future CLI / yaml-on-connect
    paths). Errors map to HTTP status codes as follows:

    - 503 if the companion is not connected (so the dashboard can show
      a "plug in your companion" hint instead of a generic 400).
    - 400 for everything else: empty / whitespace name, oversize name,
      companion ERROR payload, set_name timeout, library missing.

    The companion's flash holds the rename across reboots; the
    Meshpoint's ``self_info`` cache refreshes on the OK path so the
    Configuration card readout updates after a single dashboard
    refresh.
    """
    if _config is None:
        raise HTTPException(503, "Config not loaded")

    mc_tx = _resolve_meshcore_tx()
    if mc_tx is None or not mc_tx.connected:
        raise HTTPException(503, "MeshCore companion not connected")

    result = await mc_tx.set_companion_name(req.name)
    if not result.success:
        logger.warning(
            "Dashboard set_companion_name failed: %s", result.error
        )
        raise HTTPException(400, result.error or "Companion rejected name")

    cleaned = (req.name or "").strip()
    logger.info("MeshCore companion renamed to %r via dashboard", cleaned)

    # Persist the desired name so the USB capture source re-applies it
    # on the next connect (mirrors how channel_keys are re-synced).
    # Failure here is a soft error: the rename already stuck on the
    # companion's flash for the current session; only the on-reconnect
    # re-apply path is degraded until the user retries the save (or
    # edits local.yaml directly). Don't turn a successful rename into
    # an error response just because we couldn't write yaml.
    _config.meshcore.companion_name = cleaned
    try:
        save_section_to_yaml("meshcore", {"companion_name": cleaned})
    except PermissionError as exc:
        logger.warning(
            "Renamed companion to %r but failed to persist to "
            "local.yaml: %s. Reconnects will revert until saved.",
            cleaned,
            exc,
        )
    except Exception:
        logger.exception(
            "Renamed companion to %r but yaml persistence failed; "
            "reconnects will revert until saved.",
            cleaned,
        )

    event_type: Optional[str] = getattr(result, "event_type", None)
    return {
        "saved": True,
        "name": cleaned,
        "event_type": event_type,
    }
