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
            reference, host = runtime.dependency(state)
            rows.append({
                "id": state.name,
                "version": manifest.version if manifest else "",
                "description": manifest.description if manifest else "",
                "author": manifest.author if manifest else "",
                "source": runtime.config.plugins.get(state.name, {}).get("source"),
                "dependency": ({"id": host.name if host else reference,
                                "enabled": bool(host and runtime.config.plugins.get(host.name, {}).get("enabled") is True)}
                               if reference else None),
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
        with audit.timed_action(user=claims.subject, action="plugin.configure",
                                params={"id": plugin_id, "enabled": req.enabled}):
            async with runtime.mutation_lock:
                if runtime.states.get(plugin_id) is not state:
                    raise HTTPException(409, "Plugin changed; refresh before trying again")
                if req.enabled:
                    try:
                        chain = runtime.dependency_chain(state)
                    except ValueError as exc:
                        raise HTTPException(409, str(exc)) from exc
                    for dependency in chain:
                        if runtime.config.plugins.get(dependency.name, {}).get("enabled") is not True:
                            raise HTTPException(409, "Enable dependency first: " + dependency.name)
                updated = {**runtime.config.plugins.get(plugin_id, {}), "enabled": req.enabled}
                changes = {plugin_id: updated}
                if not req.enabled:
                    # Follow direct edges repeatedly so hooks and requires both cascade.
                    while True:
                        additions = {}
                        for dependent in runtime.states.values():
                            _, target = runtime.dependency(dependent)
                            settings = runtime.config.plugins.get(dependent.name, {})
                            if (target and target.name in changes and dependent.name not in changes
                                    and settings.get("enabled") is True):
                                additions[dependent.name] = {**settings, "enabled": False}
                        if not additions:
                            break
                        changes.update(additions)
                try:
                    save_section_to_yaml("plugins", changes)
                except OSError as exc:
                    raise HTTPException(500, "Could not save plugin configuration") from exc
                runtime.config.plugins.update(changes)
        return {"saved": True, "restart_required": True,
                "also_disabled": [name for name in changes if name != plugin_id]}

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
