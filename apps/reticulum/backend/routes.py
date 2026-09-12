"""Native Reticulum/LXMF messaging endpoints -- peer roster, message
history (reusing the existing ``messages`` table with
protocol='reticulum'), and send. Backed by ``backend/lxmf_service.py``.

Moved from ``src/api/routes/reticulum_routes.py`` as part of the
core->plugin extraction. Only the ``LxmfService`` import path changed
(now ``.lxmf_service``); ``init_routes`` is called from the plugin's
``add_service`` wire() callback once the service + message repo exist.

Read endpoints stay open to any authenticated viewer, same as core's
``messages.py`` GET routes -- only sending requires admin.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from src.api.auth.dependencies import require_admin, require_auth
from src.api.auth.jwt_session import SessionClaims
from src.storage.message_repository import MessageRepository

from . import state
from .contacts import ContactStore
from .lxmf_service import LxmfService

router = APIRouter(prefix="/api/reticulum", tags=["reticulum"])

_service: LxmfService | None = None
_message_repo: MessageRepository | None = None
_contacts: ContactStore | None = None


def init_routes(service: LxmfService, message_repo: MessageRepository) -> None:
    global _service, _message_repo, _contacts
    _service = service
    _message_repo = message_repo
    _contacts = ContactStore(state.contacts_path())


def reset_routes() -> None:
    global _service, _message_repo, _contacts
    _service = None
    _message_repo = None
    _contacts = None


def _contact_map() -> dict:
    return _contacts.all() if _contacts is not None else {}


@router.get("/status")
async def reticulum_status():
    if _service is None:
        return {"enabled": False, "running": False}
    peer_count = await _service.peer_count() if _service.own_address else 0
    cfg = state.to_dict()
    rf_on = bool(cfg.get("rnode_enabled")) and bool(
        str(cfg.get("rnode_serial_port") or "").strip()
    )
    return {
        "enabled": True,
        "running": _service.own_address is not None,
        "available": _service.available,
        "own_address": _service.own_address,
        "peer_count": peer_count,
        "node": _service.node_status(),   # None unless hosting a NomadNet node
        "propagation": _service.propagation_status(),  # None unless running a local relay
        "propagation_client": _service.propagation_client_status(),  # None until the router exists
        "radio": {
            "connected": await _service.rnode_connected() if rf_on else None,
            # what the topbar chip shows in its "freq" slot: the RNode
            # frequency when RF is configured, else the TCP backbone.
            "rf": rf_on,
            "frequency_hz": cfg.get("rnode_frequency_hz") if rf_on else None,
            "backbone": bool(cfg.get("backbone_enabled")),
        },
    }


@router.get("/peers")
async def reticulum_peers():
    if _service is None:
        raise HTTPException(503, "Reticulum companion is disabled")
    peers = await _service.list_peers()
    contacts = _contact_map()
    out = []
    for p in peers:
        row = p.to_dict()
        c = contacts.get(row["destination_hash"])
        if c:
            row["petname"] = c["petname"]
            row["trusted"] = c["trusted"]
        out.append(row)
    return out


@router.get("/announces")
async def reticulum_announces():
    """Recent announces heard (newest first) -- the Activity tab. In-memory
    ring buffer, so it starts empty on each restart."""
    if _service is None:
        raise HTTPException(503, "Reticulum companion is disabled")
    contacts = _contact_map()
    # Copy each entry -- the service hands back its own ring-buffer dicts,
    # and a later petname change / removal must not leave a stale key on them.
    out = []
    for entry in _service.announce_log():
        row = dict(entry)
        c = contacts.get(row.get("destination_hash"))
        if c:
            row["petname"] = c["petname"]
            row["trusted"] = c["trusted"]
        out.append(row)
    return out


@router.get("/peers/{destination_hash}/link")
async def reticulum_peer_link(destination_hash: str):
    """Live routing + last-known-signal info for one peer -- the Peers
    drawer's detail fetch. Deliberately per-peer, not part of GET /peers:
    hops_to()/has_path() walk RNS's path table, which the public network
    can grow into the thousands of entries, so this can't run for every
    row on every roster poll."""
    if _service is None:
        raise HTTPException(503, "Reticulum companion is disabled")
    return _service.peer_link_info(destination_hash)


@router.get("/messages/{destination_hash}")
async def reticulum_conversation(destination_hash: str, limit: int = 50):
    if _message_repo is None:
        raise HTTPException(503, "Routes not initialised")
    messages = await _message_repo.get_conversation(destination_hash, limit=limit)
    return [m.to_dict() for m in messages]


@router.get("/conversations")
async def reticulum_conversations(_claims=Depends(require_auth)):
    if _message_repo is None:
        raise HTTPException(503, "Reticulum is not initialized")
    return [c.to_dict() for c in await _message_repo.get_conversations()]


@router.post("/messages/{destination_hash}/read")
async def reticulum_mark_read(destination_hash: str, _claims=Depends(require_admin)):
    if _message_repo is None:
        raise HTTPException(503, "Reticulum is not initialized")
    await _message_repo.mark_read(destination_hash)
    return {"saved": True}


class SendRequest(BaseModel):
    destination_hash: str = Field(..., min_length=1)
    text: str = Field(..., min_length=1, max_length=10_000)


@router.post("/send")
async def reticulum_send(
    req: SendRequest, _claims: SessionClaims = Depends(require_admin),
):
    if _service is None:
        raise HTTPException(503, "Reticulum companion is disabled")
    try:
        row_id = await _service.send_message(req.destination_hash, req.text)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    except RuntimeError as exc:
        raise HTTPException(503, str(exc))
    return {"id": row_id, "status": "sent"}


@router.post("/announce")
async def reticulum_announce(_claims: SessionClaims = Depends(require_admin)):
    if _service is None:
        raise HTTPException(503, "Reticulum companion is disabled")
    try:
        _service.announce()
    except RuntimeError as exc:
        raise HTTPException(503, str(exc))
    return {"status": "announced"}


# --- LXMF propagation: client side (sync from a preferred node) ----------


@router.get("/propagation")
async def reticulum_propagation():
    """Both halves of propagation: `local` (this box running a relay, or
    None) and `client` (the outbound node + current/last sync state)."""
    if _service is None:
        raise HTTPException(503, "Reticulum companion is disabled")
    return {
        "local": _service.propagation_status(),
        "client": _service.propagation_client_status(),
    }


@router.post("/propagation/sync")
async def reticulum_propagation_sync(_claims: SessionClaims = Depends(require_admin)):
    """Pull any messages parked for us on the configured outbound
    propagation node. Returns as soon as the request is dispatched --
    poll `GET /propagation` for transfer state."""
    if _service is None:
        raise HTTPException(503, "Reticulum companion is disabled")
    result = _service.sync_propagation_messages()
    if not result.get("ok"):
        error = result.get("error") or "sync failed"
        if "propagation node" in error.lower() and state.propagation_config().get("outbound_node"):
            error = "Saved, but not active until meshpoint restarts (Settings -> System)."
        raise HTTPException(400, error)
    return {"status": "syncing"}


@router.post("/propagation/sync/cancel")
async def reticulum_propagation_sync_cancel(
    _claims: SessionClaims = Depends(require_admin),
):
    if _service is None:
        raise HTTPException(503, "Reticulum companion is disabled")
    _service.cancel_propagation_sync()
    return {"status": "cancelled"}


# --- telemetry publish ---------------------------------------------------


@router.get("/telemetry")
async def reticulum_telemetry():
    """Telemetry-publish status (or null when not configured)."""
    if _service is None:
        raise HTTPException(503, "Reticulum companion is disabled")
    return _service.telemetry_status()


@router.get("/telemetry/peers")
async def reticulum_telemetry_peers():
    """Latest telemetry received from other nodes (the collector) --
    one entry per peer, newest first, in-memory so empty after a restart."""
    if _service is None:
        raise HTTPException(503, "Reticulum companion is disabled")
    return _service.telemetry_peers()


@router.post("/telemetry/send")
async def reticulum_telemetry_send(_claims: SessionClaims = Depends(require_admin)):
    """Send one telemetry frame to the collector now."""
    if _service is None:
        raise HTTPException(503, "Reticulum companion is disabled")
    result = _service.send_telemetry()
    if not result.get("ok"):
        error = result.get("error") or "telemetry send failed"
        # The running service reads telemetry config once at startup, so a
        # just-saved collector isn't live until a meshpoint restart -- say
        # so rather than the bare "no collector" the service reports.
        if "collector" in error.lower() and state.telemetry_config().get("collectors"):
            error = "Saved, but not active until meshpoint restarts (Settings -> System)."
        raise HTTPException(400, error)
    return {"status": "sent", "sent": result.get("sent", 0), "note": result.get("error")}


# --- contacts / petnames --------------------------------------------------
# Local address book -- an operator-assigned name for a destination hash,
# stored on disk (data/reticulum/contacts.json), never announced. Reads
# stay open to any authenticated viewer (same as /peers); writes are
# admin-only (same as /send).


class ContactUpdate(BaseModel):
    petname: str = Field("", max_length=64)
    note: str = Field("", max_length=280)
    trusted: bool = False


@router.get("/contacts")
async def reticulum_contacts():
    if _contacts is None:
        raise HTTPException(503, "Reticulum companion is disabled")
    return _contacts.all()


@router.put("/contacts/{destination_hash}")
async def reticulum_contact_set(
    destination_hash: str, req: ContactUpdate,
    _claims: SessionClaims = Depends(require_admin),
):
    if _contacts is None:
        raise HTTPException(503, "Reticulum companion is disabled")
    petname = req.petname.strip()
    if not petname:
        # A cleared petname field and the drawer's "Remove" button both
        # land here -- treat an empty name as "forget this contact".
        removed = _contacts.delete(destination_hash)
        return {"status": "removed" if removed else "absent"}
    try:
        entry = _contacts.set(destination_hash, petname, req.note, req.trusted)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return {"status": "saved", "contact": entry}


@router.delete("/contacts/{destination_hash}")
async def reticulum_contact_delete(
    destination_hash: str, _claims: SessionClaims = Depends(require_admin),
):
    if _contacts is None:
        raise HTTPException(503, "Reticulum companion is disabled")
    removed = _contacts.delete(destination_hash)
    return {"status": "removed" if removed else "absent"}
