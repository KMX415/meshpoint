"""Thin LAN automation API for Home Assistant / Node-RED clients.

Aliases the dashboard endpoints operators already use, gated by
``require_automation_auth`` (optional static token or existing JWT).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from src.api.auth.dependencies import require_automation_auth
from src.api.routes import device as device_routes
from src.api.routes import messages as messages_routes
from src.api.routes import nodes as nodes_routes
from src.api.routes import packets as packets_routes

router = APIRouter(
    prefix="/api/automation",
    tags=["automation"],
    dependencies=[Depends(require_automation_auth)],
)


@router.get("/nodes")
async def automation_list_nodes(limit: int = 500, enrich: bool = True):
    return await nodes_routes.list_nodes(limit=limit, enrich=enrich)


@router.get("/nodes/{node_id}")
async def automation_get_node(node_id: str):
    return await nodes_routes.get_node(node_id)


@router.get("/packets")
async def automation_list_packets(limit: int = 100):
    return await packets_routes.list_packets(limit=limit)


@router.get("/status")
async def automation_device_status():
    return await device_routes.device_status()


class AutomationSendRequest(BaseModel):
    text: str
    channel: int = Field(0, ge=0, le=7)
    destination: str = "broadcast"
    protocol: str = "meshtastic"
    want_ack: bool = False


@router.post("/send")
async def automation_send(req: AutomationSendRequest):
    return await messages_routes.send_message(
        messages_routes.SendRequest(
            text=req.text,
            channel=req.channel,
            destination=req.destination,
            protocol=req.protocol,
            want_ack=req.want_ack,
        )
    )
