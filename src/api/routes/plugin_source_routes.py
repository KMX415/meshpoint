"""Pinned source catalogs and explicit optional downloads, never auto-enable."""
from __future__ import annotations
import asyncio
import re
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, StrictBool
from src.api.auth.dependencies import require_admin
from src.api.audit.dependencies import get_audit_writer
from src.config import save_section_to_yaml
from src.plugins import sources, installer
from src.plugins.runtime import SUPPORTED_CAPABILITIES
from src.plugins.update import replace_disabled


class AddSource(BaseModel):
    url: str
    ref: str = "main"
    trusted: StrictBool = False


class InstallPlugin(BaseModel):
    source: str
    id: str


def build_router(runtime):
    router = APIRouter(prefix="/api/plugin-sources", tags=["plugins"])
    lock = runtime.mutation_lock
    sources_enabled = runtime.config.plugin_sources_enabled is True

    def require_sources_enabled():
        if not sources_enabled:
            raise HTTPException(403, "Source installation is disabled. Set plugin_sources_enabled: true on the device and restart Meshpoint.")

    def configured():
        return runtime.config.plugins.get("_sources", {}).get("repositories", [])

    def source_for(url):
        source = next((s for s in configured() if s["url"] == url), None)
        if source is None:
            raise HTTPException(404, "Source is not configured")
        return source

    @router.get("")
    async def list_sources(_claims=Depends(require_admin)):
        return {"sources": configured(), "sources_enabled": sources_enabled}

    @router.post("")
    async def add_source(req: AddSource, claims=Depends(require_admin), audit=Depends(get_audit_writer)):
        require_sources_enabled()
        if not req.trusted:
            raise HTTPException(400, "Confirm that you trust the source before adding it")
        try:
            owner, repo = sources.parse_github_url(req.url)
            url = sources.canonical_url(owner, repo)
            ref = sources.normalise_ref(req.ref)
            commit = await asyncio.to_thread(sources.resolve_commit, url, ref)
            await asyncio.to_thread(sources.fetch_catalog, url, commit["sha"])
        except sources.PluginSourceError as exc:
            raise HTTPException(400, str(exc)) from exc
        async with lock:
            if any(s["url"] == url for s in configured()):
                raise HTTPException(409, "Source already added")
            item = {"url": url, "ref": commit["sha"], "requested_ref": ref}
            updated = {"repositories": [*configured(), item]}
            with audit.timed_action(user=claims.subject, action="plugin.source_add", params=item):
                try:
                    save_section_to_yaml("plugins", {"_sources": updated})
                except OSError as exc:
                    raise HTTPException(500, "Could not save source") from exc
                runtime.config.plugins["_sources"] = updated
        return {"source": item}

    @router.get("/catalog")
    async def catalog(url: str, _claims=Depends(require_admin)):
        source = source_for(url)
        try:
            result = await asyncio.to_thread(sources.fetch_catalog, url, source["ref"])
        except sources.PluginSourceError as exc:
            raise HTTPException(502, "Could not read source catalog") from exc
        for entry in result["plugins"]:
            entry["compatible"] = entry["compatible"] and not (
                set(entry["provides"]) - SUPPORTED_CAPABILITIES)
        for entry in result["plugins"] + result["themes"]:
            base = runtime.apps_dir if entry["kind"] == "app" else runtime.apps_dir.parent / "themes"
            entry["installed"] = (base / entry["id"]).exists()
        return result

    @router.put("")
    async def repin(req: AddSource, claims=Depends(require_admin), audit=Depends(get_audit_writer)):
        require_sources_enabled()
        if not req.trusted:
            raise HTTPException(400, "Confirm that you trust this source revision")
        async with lock:
            old = source_for(req.url)
            try:
                ref = sources.normalise_ref(req.ref)
                commit = await asyncio.to_thread(sources.resolve_commit, old["url"], ref)
                await asyncio.to_thread(sources.fetch_catalog, old["url"], commit["sha"])
            except sources.PluginSourceError as exc:
                raise HTTPException(400, str(exc)) from exc
            item = {"url": old["url"], "ref": commit["sha"], "requested_ref": ref}
            updated = {"repositories": [item if s["url"] == old["url"] else s for s in configured()]}
            with audit.timed_action(user=claims.subject, action="plugin.source_repin", params=item):
                try:
                    save_section_to_yaml("plugins", {"_sources": updated})
                except OSError as exc:
                    raise HTTPException(500, "Could not save source revision") from exc
                runtime.config.plugins["_sources"] = updated
            return {"source": item}

    @router.post("/update")
    async def update(req: InstallPlugin, claims=Depends(require_admin), audit=Depends(get_audit_writer)):
        require_sources_enabled()
        async with lock:
            source = source_for(req.source)
            state = runtime.states.get(req.id)
            if state is None or state.manifest is None:
                raise HTTPException(404, "Plugin is not installed")
            if state.manifest.locked or state.manifest.is_builtin:
                raise HTTPException(409, "Bundled plugins cannot be replaced")
            if state.registration is not None or runtime.config.plugins.get(req.id, {}).get("enabled") is True:
                raise HTTPException(409, "Disable the plugin and restart before updating")
            try:
                catalog = await asyncio.to_thread(sources.fetch_catalog, source["url"], source["ref"])
                entry = next((e for e in catalog["plugins"] if e["id"] == req.id), None)
                if entry is None:
                    raise HTTPException(404, "Plugin is absent from the new source revision")
                if not entry["compatible"] or set(entry["provides"]) - SUPPORTED_CAPABILITIES:
                    raise HTTPException(409, "Updated plugin is incompatible")
                with audit.timed_action(user=claims.subject, action="plugin.update",
                                       params={"id": req.id, "commit": source["ref"]}):
                    result = await asyncio.to_thread(replace_disabled, runtime, catalog, source, entry,
                                                     save_section_to_yaml)
                return {"updated": True, **result}
            except (sources.PluginSourceError, installer.PluginInstallError, ValueError) as exc:
                raise HTTPException(400, str(exc)) from exc
            except OSError as exc:
                raise HTTPException(500, "Update failed; previous code restored") from exc

    @router.post("/install")
    async def install(req: InstallPlugin, claims=Depends(require_admin), audit=Depends(get_audit_writer)):
        require_sources_enabled()
        source = source_for(req.source)
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]{1,38}", req.id):
            raise HTTPException(400, "Invalid plugin id")
        async with lock:
            try:
                catalog = await asyncio.to_thread(sources.fetch_catalog, source["url"], source["ref"])
                entry = next((e for e in catalog["plugins"] + catalog["themes"] if e["id"] == req.id), None)
                if entry is None:
                    raise HTTPException(404, "Plugin not found in this catalog")
                if not entry["compatible"] or (entry["kind"] == "app" and
                        set(entry["provides"]) - SUPPORTED_CAPABILITIES):
                    raise HTTPException(409, "Plugin capabilities are not supported by this build")
                if entry["kind"] == "theme" and req.id in {"dark", "high-contrast", "sunlight"}:
                    raise HTTPException(409, "Built-in themes cannot be replaced")
                base = runtime.apps_dir if entry["kind"] == "app" else runtime.apps_dir.parent / "themes"
                if (base / req.id).exists() or (base / req.id).is_symlink():
                    raise HTTPException(409, "Already installed; updates require a separate review")
                with audit.timed_action(user=claims.subject, action="plugin.install",
                                       params={"id": req.id, "url": source["url"], "commit": source["ref"]}):
                    # Persist disabled state before placing code, even if a removed
                    # plugin left an old enabled setting under the same id.
                    updated = {**runtime.config.plugins.get(req.id, {}), "enabled": False,
                               "source": {"url": source["url"], "commit": source["ref"]}}
                    try:
                        save_section_to_yaml("plugins", {req.id: updated})
                    except OSError as exc:
                        raise HTTPException(500, "Could not save disabled plugin state") from exc
                    runtime.config.plugins[req.id] = updated
                    result = await asyncio.to_thread(
                        installer.install_from_source, catalog["owner"], catalog["repo"],
                        source["ref"], entry, runtime.apps_dir,
                    )
                # Refresh inventory without re-importing or enabling downloaded code.
                runtime.discover()
                return {"installed": True, "restart_required": False, **result}
            except (sources.PluginSourceError, installer.PluginInstallError) as exc:
                raise HTTPException(400, str(exc)) from exc
    return router
