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

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from src.api.auth.dependencies import require_admin
from src.api.auth.jwt_session import SessionClaims
from src.cli.meshcore_radio_config import REGION_PRESETS
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


class CompanionRadioUpdate(BaseModel):
    preset: str | None = None
    tx_power_dbm: int | None = Field(None, ge=2, le=22)
    tx_enabled: bool | None = None


@router.put("/companion-name")
async def update_companion_name(
    req: CompanionNameUpdate,
    _claims: SessionClaims = Depends(require_admin),
) -> dict:
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


@router.put("/companion-radio")
async def update_companion_radio(
    req: CompanionRadioUpdate,
    _claims: SessionClaims = Depends(require_admin),
) -> dict:
    """Apply a MeshCore community radio preset over the live USB link.

    Resolves ``preset`` via ``REGION_PRESETS``, then
    ``MeshCoreTxClient.set_radio_params`` (set_radio + reboot + reconnect).
    Credit: javastraat/meshpoint 471d572
    """
    if _config is None:
        raise HTTPException(503, "Config not loaded")

    key = (req.preset or "").strip().upper()
    preset = REGION_PRESETS.get(key)
    if key and preset is None:
        raise HTTPException(400, f"Unknown preset '{req.preset}'")

    mc_tx = _resolve_meshcore_tx()
    if mc_tx is None or not mc_tx.connected:
        raise HTTPException(503, "MeshCore companion not connected")

    from src.radio.pimesh_runtime import provisioned
    if provisioned(_config):
        from src.radio.openhop_control import apply_radio
        try:
            await apply_radio(mc_tx, preset, req.tx_power_dbm)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        except Exception as exc:
            raise HTTPException(502, "MeshCore radio change could not be verified; inspect daemon status") from exc
        if req.tx_enabled is not None:
            save_section_to_yaml('meshcore', {'tx_enabled': req.tx_enabled})
            _config.meshcore.tx_enabled = req.tx_enabled
        if preset is None:
            return {'saved': True, 'tx_enabled': _config.meshcore.tx_enabled,
                    'tx_power_dbm': req.tx_power_dbm}
    else:
        if preset is None or req.tx_power_dbm is not None or req.tx_enabled is not None:
            raise HTTPException(400, 'Select a radio preset for this companion')
        result = await mc_tx.set_radio_params(
            preset.frequency_mhz,
            preset.bandwidth_khz,
            preset.spreading_factor,
            preset.coding_rate,
        )
        if not result.success:
            logger.warning(
                "Dashboard set_radio_params failed: %s", result.error
            )
            raise HTTPException(
                400, result.error or "Companion rejected radio params"
            )

    logger.info(
        "MeshCore radio preset %s applied via dashboard (%s)",
        key,
        preset.label,
    )
    return {
        "saved": True,
        "preset": key,
        "label": preset.label,
        "frequency_mhz": preset.frequency_mhz,
        "bandwidth_khz": preset.bandwidth_khz,
        "spreading_factor": preset.spreading_factor,
        "coding_rate": preset.coding_rate,
    }
