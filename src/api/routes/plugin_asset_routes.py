"""Expose only declared frontend files from successfully loaded plugins."""
from dataclasses import asdict
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from src.api.auth.dependencies import require_admin


def build_router(runtime):
    router = APIRouter(prefix="/api/plugin-ui", tags=["plugins"])

    @router.get("")
    async def descriptors(_claims=Depends(require_admin)):
        rows = []
        for state in runtime.states.values():
            if state.status != "loaded" or state.registration is None:
                continue
            manifest = state.manifest
            rows.append({
                "id": state.name,
                "sidebar": asdict(manifest.sidebar) if manifest.sidebar else None,
                "hook": asdict(manifest.hook) if manifest.hook else None,
                "scripts": list(manifest.frontend_scripts),
                "styles": list(manifest.frontend_styles),
            })
        return {"plugins": rows}

    @router.get("/{plugin_id}/{asset:path}")
    async def asset_file(plugin_id: str, asset: str, _claims=Depends(require_admin)):
        state = runtime.states.get(plugin_id)
        if state is None or state.status != "loaded" or state.registration is None:
            raise HTTPException(404, "Plugin is not loaded")
        manifest = state.manifest
        allowed = {*manifest.frontend_scripts, *manifest.frontend_styles}
        target = (manifest.path / asset).resolve()
        if asset not in allowed or manifest.path.resolve() not in target.parents or not target.is_file():
            raise HTTPException(404, "Asset is not declared")
        media = "text/javascript" if asset in manifest.frontend_scripts else "text/css"
        return FileResponse(target, media_type=media, headers={
            "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff",
        })

    return router
