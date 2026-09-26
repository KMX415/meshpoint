"""Authenticated PiMesh protocol switching; deliberately absent on other hardware."""

import asyncio
import time
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from src.api.auth.dependencies import require_admin, require_auth
from src.radio.pimesh_runtime import provisioned
from src.radio.pimesh_supervisor import EXECUTABLE, PHASES_BUSY, READY, STATE, read_json


class ProtocolSelection(BaseModel):
    protocol: Literal["meshtastic", "meshcore"]


def build_router(config):
    router = APIRouter(prefix="/api/pimesh", tags=["radio"])

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

    return router
