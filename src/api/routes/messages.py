"""REST API endpoints for mesh messaging.

Provides send, conversation list, conversation history, channel
messages, contacts, and TX status endpoints for the local dashboard.
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from src.api.message_name_resolver import MessageNameResolver
from src.config import AppConfig
from src.storage.message_repository import (
    BROADCAST_NODE_MC,
    BROADCAST_NODE_MT,
    MessageRepository,
)
from src.storage.packet_repository import PacketRepository
from src.transmit.meshcore_tx_client import MeshCoreTxClient
from src.transmit.tx_service import PRESET_DISPLAY_NAMES, TxService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/messages", tags=["messages"])

_tx_service: TxService | None = None
_message_repo: MessageRepository | None = None
_node_repo = None
_meshcore_tx: MeshCoreTxClient | None = None
_config: AppConfig | None = None
_name_resolver: MessageNameResolver | None = None


def init_routes(
    tx_service: TxService | None,
    message_repo: MessageRepository,
    node_repo,
    meshcore_tx: MeshCoreTxClient | None = None,
    config: AppConfig | None = None,
    packet_repo: PacketRepository | None = None,
) -> None:
    global _tx_service, _message_repo, _node_repo, _meshcore_tx, _config, _name_resolver
    _tx_service = tx_service
    _message_repo = message_repo
    _node_repo = node_repo
    _meshcore_tx = meshcore_tx
    _config = config
    _name_resolver = MessageNameResolver(node_repo, meshcore_tx, packet_repo)


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
    node_name = await _resolve_display_name(node_id, req.protocol)

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


@router.post("/advert")
async def send_meshcore_advert(flood: bool = False):
    """Broadcast a MeshCore advertisement from the USB companion.

    Independent of /send so it bypasses the empty-text validation
    and routes to the dedicated MeshCore advert path instead of
    the text-message TX pipeline.
    """
    if _meshcore_tx is None or not _meshcore_tx.connected:
        raise HTTPException(503, "MeshCore companion not connected")
    result = await _meshcore_tx.send_advert(flood=flood)
    if not result.success:
        logger.warning("Dashboard MeshCore advert failed: %s", result.error)
    return {
        "success": result.success,
        "error": result.error,
        "event_type": getattr(result, "event_type", None),
    }


@router.get("/conversations")
async def get_conversations(include_overheard: bool = False):
    if _message_repo is None:
        raise HTTPException(503, "Message storage not available")
    conversations = await _message_repo.get_conversations(include_overheard)
    return await _enrich_conversations([c.to_dict() for c in conversations])


@router.get("/conversation/{node_id:path}")
async def get_conversation(
    node_id: str, limit: int = 50, before: Optional[str] = None
):
    if _message_repo is None:
        raise HTTPException(503, "Message storage not available")
    messages = await _message_repo.get_conversation(node_id, limit, before)
    return await _enrich_messages([m.to_dict() for m in messages])


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
        default_name = _config.meshtastic.primary_channel_name
        if not default_name:
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
        if _config:
            for i, (name, _key) in enumerate(
                _config.meshcore.channel_keys.items(), start=1
            ):
                channels.append({
                    "protocol": "meshcore",
                    "channel": i,
                    "name": name,
                    "node_id": f"{BROADCAST_NODE_MC}:{i}",
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
                name = await _resolve_display_name(canonical, "meshcore") or canonical
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


async def _resolve_display_name(
    node_id: str, protocol: str = "", fallback: str = ""
) -> str:
    if _name_resolver is None:
        return fallback
    return await _name_resolver.resolve(node_id, protocol, fallback)


async def _enrich_conversations(conversations: list[dict]) -> list[dict]:
    if _name_resolver is None:
        return conversations
    return [
        await _name_resolver.apply_to_conversation_dict(convo)
        for convo in conversations
    ]


async def _enrich_messages(messages: list[dict]) -> list[dict]:
    if _name_resolver is None or not messages:
        return messages
    return [
        await _name_resolver.apply_to_message_dict(msg)
        for msg in messages
    ]
