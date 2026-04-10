"""REST API endpoints for mesh messaging.

Provides send, conversation list, conversation history, channel
messages, contacts, and TX status endpoints for the local dashboard.
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from src.config import AppConfig
from src.storage.message_repository import (
    BROADCAST_NODE_MC,
    BROADCAST_NODE_MT,
    MessageRepository,
)
from src.transmit.meshcore_tx_client import MeshCoreTxClient
from src.transmit.tx_service import PRESET_DISPLAY_NAMES, TxService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/messages", tags=["messages"])

_tx_service: TxService | None = None
_message_repo: MessageRepository | None = None
_node_repo = None
_meshcore_tx: MeshCoreTxClient | None = None
_config: AppConfig | None = None


def init_routes(
    tx_service: TxService | None,
    message_repo: MessageRepository,
    node_repo,
    meshcore_tx: MeshCoreTxClient | None = None,
    config: AppConfig | None = None,
) -> None:
    global _tx_service, _message_repo, _node_repo, _meshcore_tx, _config
    _tx_service = tx_service
    _message_repo = message_repo
    _node_repo = node_repo
    _meshcore_tx = meshcore_tx
    _config = config


class SendRequest(BaseModel):
    text: str
    destination: str = "broadcast"
    protocol: str = "meshtastic"
    channel: int = 0
    want_ack: bool = False


@router.post("/send")
async def send_message(req: SendRequest):
    if _tx_service is None:
        raise HTTPException(503, "Transmit service not available")
    if _message_repo is None:
        raise HTTPException(503, "Message storage not available")

    if not req.text.strip():
        raise HTTPException(400, "Message text cannot be empty")
    if len(req.text) > 228:
        raise HTTPException(400, "Message too long (max 228 bytes)")

    result = await _tx_service.send_text(
        text=req.text,
        destination=req.destination,
        protocol=req.protocol,
        channel=req.channel,
        want_ack=req.want_ack,
    )

    node_id = _resolve_node_id(req.destination, req.protocol, req.channel)
    node_name = await _lookup_node_name(node_id)

    if result.success:
        await _message_repo.save_sent(
            text=req.text,
            node_id=node_id,
            node_name=node_name,
            protocol=req.protocol,
            channel=req.channel,
            packet_id=result.packet_id,
            status="sent",
        )

    return {
        "success": result.success,
        "packet_id": result.packet_id,
        "protocol": result.protocol,
        "timestamp": result.timestamp,
        "airtime_ms": result.airtime_ms,
        "error": result.error,
    }


@router.get("/conversations")
async def get_conversations(include_overheard: bool = False):
    if _message_repo is None:
        raise HTTPException(503, "Message storage not available")
    conversations = await _message_repo.get_conversations(include_overheard)
    return [c.to_dict() for c in conversations]


@router.get("/conversation/{node_id:path}")
async def get_conversation(
    node_id: str, limit: int = 50, before: Optional[str] = None
):
    if _message_repo is None:
        raise HTTPException(503, "Message storage not available")
    messages = await _message_repo.get_conversation(node_id, limit, before)
    return [m.to_dict() for m in messages]


@router.post("/conversation/{node_id:path}/read")
async def mark_conversation_read(node_id: str):
    if _message_repo is None:
        raise HTTPException(503, "Message storage not available")
    await _message_repo.mark_read(node_id)
    return {"status": "ok"}


@router.delete("/conversation/{node_id:path}")
async def delete_conversation(node_id: str):
    if _message_repo is None:
        raise HTTPException(503, "Message storage not available")
    deleted = await _message_repo.delete_conversation(node_id)
    return {"status": "ok", "deleted": deleted}


@router.delete("/all")
async def delete_all_messages():
    if _message_repo is None:
        raise HTTPException(503, "Message storage not available")
    deleted = await _message_repo.delete_all_messages()
    return {"status": "ok", "deleted": deleted}


@router.get("/channels")
async def get_channels():
    default_name = "LongFast"
    if _config:
        sf = _config.radio.spreading_factor
        bw = int(_config.radio.bandwidth_khz)
        default_name = PRESET_DISPLAY_NAMES.get((sf, bw), "Custom")

    channels = [
        {
            "protocol": "meshtastic",
            "channel": 0,
            "name": default_name,
            "node_id": f"{BROADCAST_NODE_MT}:0",
        }
    ]

    if _config:
        for i, (name, _key) in enumerate(
            _config.meshtastic.channel_keys.items(), start=1
        ):
            channels.append({
                "protocol": "meshtastic",
                "channel": i,
                "name": name,
                "node_id": f"{BROADCAST_NODE_MT}:{i}",
            })

    if _meshcore_tx and _meshcore_tx.connected:
        channels.append({
            "protocol": "meshcore",
            "channel": 0,
            "name": "Public",
            "node_id": f"{BROADCAST_NODE_MC}:0",
        })

    return channels


@router.get("/contacts")
async def get_contacts():
    contacts = []

    _synthetic = {"rf_log", "raw", "mc:channel", "unknown", ""}
    if _node_repo:
        all_nodes = await _node_repo.get_all()
        for node in all_nodes:
            n = node if isinstance(node, dict) else node.to_dict()
            nid = n.get("node_id", "")
            if nid in _synthetic or nid.startswith("mc:"):
                continue
            contacts.append({
                "node_id": nid,
                "name": n.get("long_name") or n.get("short_name") or nid,
                "protocol": n.get("protocol", "meshtastic"),
                "last_heard": n.get("last_heard", ""),
            })

    if _meshcore_tx and _meshcore_tx.connected:
        mc_contacts = await _meshcore_tx.get_contacts()
        for contact in mc_contacts:
            pk = contact.get("public_key", "")
            canonical = pk[:12].lower() if len(pk) >= 12 else pk.lower()
            name = contact.get("name", "")
            if not name or name.lower() == canonical:
                name = await _lookup_node_name(canonical) or canonical
            contacts.append({
                "node_id": canonical,
                "name": name,
                "protocol": "meshcore",
                "last_heard": "",
            })

    return contacts


@router.get("/status")
async def get_status():
    mt_status = {"enabled": False, "node_id": ""}
    mc_status = {"enabled": False, "connected": False, "companion_name": ""}

    if _tx_service:
        mt_status["enabled"] = _tx_service.meshtastic_enabled
        mt_status["node_id"] = f"!{_tx_service.source_node_id:08x}"
        mc_status["enabled"] = _tx_service.meshcore_enabled

    if _meshcore_tx and _meshcore_tx.connected:
        mc_status["connected"] = True
        radio = await _meshcore_tx.get_radio_info()
        if radio:
            mc_status["companion_name"] = radio.name

    return {"meshtastic": mt_status, "meshcore": mc_status}


def _is_hex_only(s: str) -> bool:
    try:
        int(s, 16)
        return len(s) >= 6
    except ValueError:
        return False


def _resolve_node_id(
    destination: str, protocol: str, channel: int
) -> str:
    dest_lower = destination.lower()
    if dest_lower in ("broadcast", "all", "0", "ffffffff", "ffff"):
        return f"broadcast:{protocol}:{channel}"
    return destination


async def _lookup_node_name(node_id: str) -> str:
    if node_id.startswith("broadcast:"):
        return "Broadcast"
    if _node_repo:
        try:
            for candidate in (node_id, node_id.upper(), node_id.lower()):
                node = await _node_repo.get_by_id(candidate)
                if node:
                    n = node if isinstance(node, dict) else node.to_dict()
                    name = n.get("long_name") or n.get("short_name") or ""
                    if name and name != candidate:
                        return name
        except Exception:
            pass
    if _meshcore_tx and _meshcore_tx.connected:
        try:
            mc_contacts = await _meshcore_tx.get_contacts()
            nid_lower = node_id.lower()
            for c in mc_contacts:
                pk = c.get("public_key", "").lower()
                name = c.get("name", "")
                if not name or _is_hex_only(name):
                    continue
                if pk.startswith(nid_lower) or nid_lower.startswith(pk[:8]):
                    return name
        except Exception:
            pass
    if _node_repo:
        try:
            row = await _node_repo._db.fetch_one(
                "SELECT node_id, long_name FROM nodes "
                "WHERE node_id LIKE 'mc:%' AND protocol = 'meshcore' "
                "AND node_id NOT IN ('mc:channel')",
            )
            if row:
                rn = row["long_name"] or row["node_id"][3:]
                if rn and not _is_hex_only(rn):
                    return rn
        except Exception:
            pass
    return ""
