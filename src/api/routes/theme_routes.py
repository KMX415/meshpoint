"""Dashboard theme endpoints.

``GET /api/themes`` -- the theme picker's manifest (list + the
server-configured default). Unauthenticated on purpose: it carries no
device data and the ``theme.css`` files it points at are already served
unauthenticated through the static mount.

``PUT /api/config/dashboard/theme`` -- admin-only; sets the default theme
for browsers that haven't picked one (``dashboard.theme`` in local.yaml).

``POST /api/themes`` / ``DELETE /api/themes/{id}`` -- admin-only; write or
remove a drop-in theme under ``plugins/themes/`` (see
``src/api/theme_store.py``). No restart: ``GET /api/themes`` re-scans per
request and the ``<link>`` injection runs per page serve.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from src.api.audit import AuditLogWriter
from src.api.audit.dependencies import get_audit_writer
from src.api.auth.jwt_session import SessionClaims
from src.api.auth.dependencies import require_admin
from src.api.theme_registry import DEFAULT_THEME_ID, scan_themes
from src.api.theme_store import ThemeSaveError, delete_theme, save_theme
from src.config import AppConfig, save_section_to_yaml

_ERR_STATUS = {
    "slug": 400, "label": 400, "import": 400,
    "reserved": 409, "toobig": 413, "perm": 403,
}

router = APIRouter(prefix="/api", tags=["themes"])

_themes_dir: Path | None = None
_plugin_themes_dir: Path | None = None
_config: AppConfig | None = None


def init_routes(
    themes_dir: Path,
    plugin_themes_dir: Path | None = None,
    config: AppConfig | None = None,
) -> None:
    global _themes_dir, _plugin_themes_dir, _config
    _themes_dir = themes_dir
    _plugin_themes_dir = plugin_themes_dir
    _config = config


def _theme_ids() -> set[str]:
    if _themes_dir is None:
        return {DEFAULT_THEME_ID}
    return {t["id"] for t in scan_themes(_themes_dir, _plugin_themes_dir)}


def _builtin_ids() -> set[str]:
    """Ids that live in frontend/themes/ -- never writable/deletable here."""
    if _themes_dir is None:
        return {DEFAULT_THEME_ID}
    return {t["id"] for t in scan_themes(_themes_dir)}


def _current_default() -> str:
    configured = getattr(getattr(_config, "dashboard", None), "theme", None)
    if configured and configured in _theme_ids():
        return configured
    return DEFAULT_THEME_ID


@router.get("/themes")
async def list_themes() -> dict:
    themes = (
        scan_themes(_themes_dir, _plugin_themes_dir)
        if _themes_dir is not None
        else []
    )
    return {"themes": themes, "default": _current_default()}


class ThemeUpdate(BaseModel):
    theme: str


@router.put("/config/dashboard/theme")
async def set_default_theme(
    req: ThemeUpdate,
    _claims: SessionClaims = Depends(require_admin),
    audit: AuditLogWriter = Depends(get_audit_writer),
) -> dict:
    theme = (req.theme or "").strip()
    if theme not in _theme_ids():
        raise HTTPException(400, f"Unknown theme {theme!r}")

    with audit.timed_action(
        user=_claims.subject,
        action="config.dashboard_theme",
        params={"theme": theme},
    ):
        try:
            save_section_to_yaml("dashboard", {"theme": theme})
        except PermissionError as exc:
            raise HTTPException(403, str(exc)) from exc

    if _config is not None:
        _config.dashboard.theme = theme

    return {"saved": True, "theme": theme}


class ThemeSave(BaseModel):
    id: str
    label: str
    css: str
    icon: str = "palette"
    author: str = ""
    homepage: str = ""
    description: str = ""


@router.post("/themes")
async def save_theme_route(
    req: ThemeSave,
    _claims: SessionClaims = Depends(require_admin),
    audit: AuditLogWriter = Depends(get_audit_writer),
) -> dict:
    if _plugin_themes_dir is None:
        raise HTTPException(503, "No plugin theme directory is configured.")

    with audit.timed_action(
        user=_claims.subject,
        action="theme.save",
        params={"id": req.id},
    ) as ctx:
        try:
            result = save_theme(_plugin_themes_dir, req.model_dump(), _builtin_ids())
        except ThemeSaveError as exc:
            raise HTTPException(_ERR_STATUS.get(exc.code, 400), exc.message) from exc
        ctx.params["overwritten"] = result["overwritten"]

    return {"saved": True, **result}


@router.delete("/themes/{theme_id}")
async def delete_theme_route(
    theme_id: str,
    _claims: SessionClaims = Depends(require_admin),
    audit: AuditLogWriter = Depends(get_audit_writer),
) -> dict:
    if _plugin_themes_dir is None:
        raise HTTPException(503, "No plugin theme directory is configured.")

    with audit.timed_action(
        user=_claims.subject,
        action="theme.delete",
        params={"id": theme_id},
    ):
        try:
            delete_theme(_plugin_themes_dir, theme_id, _builtin_ids())
        except ThemeSaveError as exc:
            raise HTTPException(_ERR_STATUS.get(exc.code, 400), exc.message) from exc
        except FileNotFoundError as exc:
            raise HTTPException(404, f"No such theme {theme_id!r}.") from exc

        # Don't leave the server default pointing at a deleted theme.
        if _config is not None and getattr(_config.dashboard, "theme", None) == theme_id:
            try:
                save_section_to_yaml("dashboard", {"theme": DEFAULT_THEME_ID})
            except PermissionError:
                pass
            _config.dashboard.theme = DEFAULT_THEME_ID

    return {"deleted": True, "id": theme_id}
