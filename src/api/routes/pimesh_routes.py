"""Authenticated PiMesh protocol switching; deliberately absent on other hardware."""

import asyncio
import time
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict

from src.api.auth.dependencies import require_admin, require_auth
from src.radio.pimesh_runtime import provisioned
from src.radio.pimesh_supervisor import EXECUTABLE, PHASES_BUSY, READY, STATE, read_json


class ProtocolSelection(BaseModel):
    protocol: Literal["meshtastic", "meshcore"]


class BehaviorSelection(ProtocolSelection):
    model_config = ConfigDict(extra="forbid")
    role: str | None = None
    rebroadcast_mode: str | None = None
    mode: Literal["monitor", "forward", "no_tx"] | None = None


def build_router(config):
    router = APIRouter(prefix="/api/pimesh", tags=["radio"])
    operation_lock = asyncio.Lock()

    def require_pimesh():
        if not provisioned(config):
            raise HTTPException(404, "PiMesh is not provisioned on this installation")

    @router.get("/status", dependencies=[Depends(require_auth)])
    async def status():
        require_pimesh()
        state = read_json(STATE)
        health = read_json(READY)
        return {
            **state,
            "board": config.device.radio_hat,
            "connected": health.get("ready") is True
            and health.get("operation_id") == state.get("operation_id")
            and health.get("protocol") == state.get("active")
            and time.time() - health.get("updated_at", 0) < 45,
            "switching": state.get("phase") in PHASES_BUSY,
        }

    @router.post("/protocol", status_code=202, dependencies=[Depends(require_admin)])
    async def switch(selection: ProtocolSelection):
        if operation_lock.locked():
            raise HTTPException(409, "A radio settings operation is running")
        async with operation_lock:
            return await start_switch(selection)

    async def start_switch(selection):
        require_pimesh()
        if read_json(STATE).get("phase") in PHASES_BUSY:
            raise HTTPException(409, "A protocol switch is already running")
        process = await asyncio.create_subprocess_exec(
            "sudo",
            "-n",
            EXECUTABLE,
            "request",
            selection.protocol,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            await asyncio.wait_for(process.communicate(), timeout=20)
        except TimeoutError:
            process.kill()
            await process.wait()
            raise HTTPException(
                503, "Switch request timed out; check radio status before retrying"
            )
        if process.returncode:
            raise HTTPException(
                409, "Unable to start switch; check radio status and service logs"
            )
        return await status()

    async def behavior_operation(protocol, selection=None):
        current = await status()
        if current["switching"] or current.get("active") != protocol:
            raise HTTPException(409, "Radio protocol changed or is switching; reload settings")
        if not current["connected"]:
            raise HTTPException(503, "Radio is disconnected; reload when connected")
        try:
            if protocol == "meshcore":
                from src.radio.openhop_control import apply_mode, read_mode

                if selection is not None:
                    if selection.mode is None or selection.role is not None or selection.rebroadcast_mode is not None:
                        raise ValueError("MeshCore requires only a forwarding mode")
                    result = await apply_mode(selection.mode)
                else:
                    result = await read_mode()
            else:
                from src.api.routes.config_routes import _pimesh_meshtastic_bridge
                from src.capture.meshtasticd_device import validate_device

                payload = None
                if selection is not None:
                    if selection.mode is not None:
                        raise ValueError("Meshtastic requires a role and rebroadcast mode")
                    validate_device(selection.role, selection.rebroadcast_mode)
                    payload = {"role": selection.role, "rebroadcast_mode": selection.rebroadcast_mode}
                source = _pimesh_meshtastic_bridge()
                if source is None:
                    raise HTTPException(503, "Meshtastic radio unavailable")
                ok, result = await asyncio.to_thread(source.request_device, payload)
                if not ok:
                    raise RuntimeError("Device operation unconfirmed")
            after = await status()
            if after["switching"] or after.get("operation_id") != current.get("operation_id"):
                raise HTTPException(409, "Radio changed during request; reload settings")
            return {"protocol": protocol, **result}
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        except HTTPException:
            raise
        except Exception as exc:
            # Backend errors can contain credentials or private configuration.
            raise HTTPException(503, "Radio settings unconfirmed. The radio may be restarting; reload before retrying.") from exc

    @router.get("/behavior", dependencies=[Depends(require_auth)])
    async def get_behavior(protocol: Literal["meshtastic", "meshcore"]):
        require_pimesh()
        if operation_lock.locked():
            raise HTTPException(409, "A radio settings operation is running")
        async with operation_lock:
            return await behavior_operation(protocol)

    @router.put("/behavior", dependencies=[Depends(require_admin)])
    async def set_behavior(selection: BehaviorSelection):
        require_pimesh()
        if operation_lock.locked():
            raise HTTPException(409, "A radio settings operation is running")
        async with operation_lock:
            return await behavior_operation(selection.protocol, selection)

    return router
