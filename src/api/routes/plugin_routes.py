"""Authenticated inventory and enablement for optional plugins."""
from __future__ import annotations
import shutil
import uuid
import asyncio

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, StrictBool

from src.api.auth.dependencies import require_admin
from src.api.audit.dependencies import get_audit_writer
from src.config import save_section_to_yaml
from src.plugins.dependencies import dependency_report
from src.plugins import python_dependencies


def build_router(runtime):
    router = APIRouter(prefix="/api/plugins", tags=["plugins"])

    @router.get("")
    async def inventory(_claims=Depends(require_admin)):
        rows = []
        for state in runtime.states.values():
            manifest = state.manifest
            live_error = next((getattr(service, "failure", "") for owner, service in runtime.live
                               if owner == state.name and getattr(service, "failure", "")), "")
            enabled = runtime.config.plugins.get(state.name, {}).get("enabled") is True
            rows.append({
                "id": state.name,
                "version": manifest.version if manifest else "",
                "description": manifest.description if manifest else "",
                "author": manifest.author if manifest else "",
                "provides": list(manifest.provides) if manifest else [],
                "packages": list(manifest.apt) if manifest else [],
                "dependencies": dependency_report(manifest) if manifest else None,
                "python_setup": state.name == "reticulum",
                "python_ready": python_dependencies.is_ready(runtime.apps_dir) if state.name == "reticulum" else True,
                "has_setup": bool(manifest and manifest.setup),
                "setup_instructions": "Review the plugin README and install its listed dependencies on the device. Meshpoint does not run downloaded setup scripts as root.",
                "locked": bool(manifest and (manifest.locked or manifest.is_builtin)),
                "enabled": enabled, "status": "failed" if live_error else state.status,
                "error": live_error or state.error,
                "restart_required": enabled != (state.registration is not None) or bool(live_error),
            })
        return {"plugins": rows}

    @router.post("/{plugin_id}/dependencies")
    async def setup_python(plugin_id: str, claims=Depends(require_admin), audit=Depends(get_audit_writer)):
        if plugin_id != "reticulum" or plugin_id not in runtime.states:
            raise HTTPException(404, "No reviewed Python dependency recipe for this plugin")
        async with runtime.mutation_lock:
            if runtime.states[plugin_id].registration is not None:
                raise HTTPException(409, "Disable and restart the plugin before changing its dependencies")
            with audit.timed_action(user=claims.subject, action="plugin.dependencies", params={"id": plugin_id}):
                try:
                    return await asyncio.to_thread(python_dependencies.install_reticulum, runtime.apps_dir)
                except (OSError, ValueError) as exc:
                    raise HTTPException(400, "Dependency download or verification failed; core environment unchanged") from exc

    @router.put("/{plugin_id}")
    async def configure(plugin_id: str, req: EnablePlugin,
                        claims=Depends(require_admin), audit=Depends(get_audit_writer)):
        state = runtime.states.get(plugin_id)
        if state is None:
            raise HTTPException(404, "Plugin is not installed")
        if req.enabled and (state.manifest is None or state.status == "incompatible"):
            raise HTTPException(409, "Plugin is not compatible with this build")
        if req.enabled and state.manifest.hook:
            host = next((s for s in runtime.states.values() if s.manifest and s.manifest.sidebar
                         and s.manifest.sidebar.route == state.manifest.hook.host), None)
            if host is None or runtime.config.plugins.get(host.name, {}).get("enabled") is not True:
                raise HTTPException(409, "Install and enable the host page first: " + state.manifest.hook.host)
        existing = runtime.config.plugins.get(plugin_id, {})
        updated = {**existing, "enabled": req.enabled}
        with audit.timed_action(user=claims.subject, action="plugin.configure",
                                params={"id": plugin_id, "enabled": req.enabled}):
            async with runtime.mutation_lock:
                if runtime.states.get(plugin_id) is not state:
                    raise HTTPException(409, "Plugin changed; refresh before trying again")
                updated = {**runtime.config.plugins.get(plugin_id, {}), "enabled": req.enabled}
                try:
                    save_section_to_yaml("plugins", {plugin_id: updated})
                except OSError as exc:
                    raise HTTPException(500, "Could not save plugin configuration") from exc
                runtime.config.plugins[plugin_id] = updated
        return {"saved": True, "restart_required": True}

    @router.delete("/{plugin_id}")
    async def uninstall(plugin_id: str, claims=Depends(require_admin), audit=Depends(get_audit_writer)):
        async with runtime.mutation_lock:
            state = runtime.states.get(plugin_id)
            if state is None:
                raise HTTPException(404, "Plugin is not installed")
            if state.manifest and (state.manifest.locked or state.manifest.is_builtin):
                raise HTTPException(409, "Bundled plugins cannot be removed")
            settings = runtime.config.plugins.get(plugin_id, {})
            if settings.get("enabled") is True or state.registration is not None:
                raise HTTPException(409, "Disable the plugin and restart Meshpoint before removing it")
            target = runtime.apps_dir / plugin_id
            if target.is_symlink() or target.resolve().parent != runtime.apps_dir.resolve():
                raise HTTPException(409, "Plugin directory is not safe to remove")
            # Keep settings and user data. Only installed code leaves discovery.
            quarantine = runtime.apps_dir.parent / "removed" / (plugin_id + "-" + uuid.uuid4().hex)
            with audit.timed_action(user=claims.subject, action="plugin.uninstall", params={"id": plugin_id}):
                try:
                    quarantine.parent.mkdir(parents=True, exist_ok=True)
                    target.rename(quarantine)
                except OSError as exc:
                    raise HTTPException(500, "Could not remove plugin files") from exc
                runtime.states.pop(plugin_id)
                try:
                    shutil.rmtree(quarantine)
                except OSError:
                    return {"removed": True, "settings_retained": True, "cleanup_pending": True}
            return {"removed": True, "settings_retained": True, "cleanup_pending": False}

    return router


class EnablePlugin(BaseModel):
    enabled: StrictBool
