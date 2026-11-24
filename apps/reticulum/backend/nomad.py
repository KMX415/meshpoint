"""NomadNet page/file fetching over Reticulum Links.

A NomadNet node (aspect ``nomadnetwork.node``) is a small BBS-style server
that hosts pages written in Micron markup, served over standard RNS
``Link`` + ``Request`` primitives -- the same ones ``lxmf_service``'s
``send_message()`` already uses (path discovery, ``Identity.recall``).
This module wraps that callback-based API in ``async`` calls that a
FastAPI route can ``await``.

Ported in spirit from reticulum-meshchat's ``NomadnetDownloader``
(``meshchat.py``, MIT) -- same Link-cache-per-destination, same
request-path-then-link-then-request sequence. Pages come back as UTF-8
Micron text; files as raw bytes (from a ``/file/...`` path).

RNS is a process-global singleton: once ``LxmfService.start()`` has run
``RNS.Reticulum()``, ``RNS.Transport`` / ``RNS.Link`` work here with no
extra attach. Read-only browsing needs no local identity (NomadNet Links
are anonymous unless a page explicitly requires ``link.identify()``).

Kept importable without ``rns`` -- the fetchers return an error result
rather than raising when RNS isn't available.
"""

from __future__ import annotations

import asyncio
import io
import logging
import os
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

try:
    import RNS
except ImportError:  # not installed -- e.g. Mac dev environment
    RNS = None

# Established links, keyed by destination_hash hex -- reused across page
# navigations on the same node instead of re-linking on every click.
_links: dict = {}

# Defaults, overridable from plugins.reticulum.nomad_timeout_s (see
# state.py) via set_timeouts() -- multi-hop LoRa paths need more headroom
# than reticulum-meshchat's TCP-backbone-first 15s.
_path_lookup_timeout_s = 20
_link_timeout_s = 20
_request_timeout_s = 30


def set_timeouts(base_s: Optional[int]) -> None:
    """Scale the three timeouts from one ``nomad_timeout_s`` knob
    (``None`` / falsy -> defaults). base is the link/path budget;
    request gets 1.5x."""
    global _path_lookup_timeout_s, _link_timeout_s, _request_timeout_s
    if not base_s:
        _path_lookup_timeout_s = _link_timeout_s = 20
        _request_timeout_s = 30
        return
    base = max(5, int(base_s))
    _path_lookup_timeout_s = base
    _link_timeout_s = base
    _request_timeout_s = int(base * 1.5)


@dataclass
class NomadResult:
    ok: bool
    content: Optional[str] = None       # Micron markup, for a page
    file_name: Optional[str] = None     # for a file
    file_bytes: Optional[bytes] = None  # for a file
    error: Optional[str] = None
    destination_hash: str = ""
    path: str = ""


def available() -> bool:
    """True once RNS is importable AND a Reticulum instance exists in this
    process (i.e. the reticulum plugin's LxmfService has started)."""
    if RNS is None:
        return False
    try:
        return RNS.Reticulum.get_instance() is not None
    except Exception:  # noqa: BLE001 -- old RNS without get_instance(); treat as unavailable
        return False


async def _ensure_path(dest_hash: bytes) -> bool:
    loop = asyncio.get_running_loop()
    if RNS.Transport.has_path(dest_hash):
        return True
    RNS.Transport.request_path(dest_hash)
    deadline = loop.time() + _path_lookup_timeout_s
    while not RNS.Transport.has_path(dest_hash) and loop.time() < deadline:
        await asyncio.sleep(0.1)
    return RNS.Transport.has_path(dest_hash)


async def _ensure_link(destination_hash_hex: str, dest_hash: bytes):
    """Return an ACTIVE RNS.Link to the node, from cache or freshly made."""
    loop = asyncio.get_running_loop()
    link = _links.get(destination_hash_hex)
    if link is not None and link.status == RNS.Link.ACTIVE:
        return link

    identity = RNS.Identity.recall(dest_hash)
    if identity is None:
        return None

    destination = RNS.Destination(
        identity, RNS.Destination.OUT, RNS.Destination.SINGLE,
        "nomadnetwork", "node",
    )
    link = RNS.Link(destination)
    _links[destination_hash_hex] = link
    deadline = loop.time() + _link_timeout_s
    while link.status != RNS.Link.ACTIVE and loop.time() < deadline:
        await asyncio.sleep(0.1)
    return link if link.status == RNS.Link.ACTIVE else None


async def _request(destination_hash_hex: str, path: str, field_data: Optional[dict]):
    """Shared path/link/request core. Returns ``("ok", receipt)`` or
    ``("err", message)`` -- caller decodes the receipt's response."""
    if not available():
        return "err", "Reticulum is not running (enable + set up the reticulum plugin)"

    try:
        dest_hash = bytes.fromhex(destination_hash_hex)
    except ValueError:
        return "err", "Invalid destination hash"

    if not await _ensure_path(dest_hash):
        return "err", "No path to that node -- it may be offline or unreachable"

    link = await _ensure_link(destination_hash_hex, dest_hash)
    if link is None:
        return "err", "Could not establish a link to that node"

    loop = asyncio.get_running_loop()
    fut: asyncio.Future = loop.create_future()

    def _on_response(receipt) -> None:
        if not fut.done():
            loop.call_soon_threadsafe(fut.set_result, ("ok", receipt))

    def _on_failed(receipt=None) -> None:
        if not fut.done():
            loop.call_soon_threadsafe(fut.set_result, ("err", "the node rejected or dropped the request"))

    try:
        link.request(
            path,
            data=field_data or None,
            response_callback=_on_response,
            failed_callback=_on_failed,
            timeout=_request_timeout_s,
        )
    except Exception as exc:  # noqa: BLE001
        return "err", f"Request could not be sent: {exc}"

    try:
        return await asyncio.wait_for(fut, timeout=_request_timeout_s + 5)
    except asyncio.TimeoutError:
        return "err", "Timed out waiting for a response"


async def fetch_page(
    destination_hash_hex: str,
    path: str = "/page/index.mu",
    field_data: Optional[dict] = None,
) -> NomadResult:
    """Fetch one NomadNet page. ``field_data`` (optional) is a dict of
    already-prefixed (``field_``/``var_``) form values."""
    result = NomadResult(ok=False, destination_hash=destination_hash_hex, path=path)
    kind, payload = await _request(destination_hash_hex, path, field_data)
    if kind == "err":
        result.error = payload
        return result

    try:
        data = payload.response
        if isinstance(data, (bytes, bytearray)):
            result.content = bytes(data).decode("utf-8", errors="replace")
        else:
            result.content = str(data)
        result.ok = True
    except Exception as exc:  # noqa: BLE001
        result.error = f"Could not decode the page: {exc}"
    return result


def _extract_file(response, receipt) -> tuple[str, bytes]:
    """NomadNet file responses come as an io.BufferedReader, a
    ``[bytes, {name: b"..."}]`` list, or (older) ``[name, bytes]``."""
    name = "downloaded_file"
    if isinstance(response, io.BufferedReader):
        meta = getattr(receipt, "metadata", None)
        if isinstance(meta, dict) and meta.get("name"):
            name = os.path.basename(meta["name"].decode("utf-8", errors="replace"))
        return name, response.read()
    if isinstance(response, (list, tuple)) and len(response) == 2:
        a, b = response
        if isinstance(b, dict):
            if b.get("name"):
                name = os.path.basename(b["name"].decode("utf-8", errors="replace"))
            return name, bytes(a)
        if isinstance(a, (bytes, bytearray)):
            return name, bytes(a)
        return os.path.basename(str(a)), bytes(b)
    if isinstance(response, (bytes, bytearray)):
        return name, bytes(response)
    raise ValueError("unsupported file response shape")


async def fetch_file(destination_hash_hex: str, path: str) -> NomadResult:
    """Fetch a file from a ``/file/...`` path -> raw bytes + a filename."""
    result = NomadResult(ok=False, destination_hash=destination_hash_hex, path=path)
    kind, payload = await _request(destination_hash_hex, path, None)
    if kind == "err":
        result.error = payload
        return result
    try:
        name, data = _extract_file(payload.response, payload)
        result.ok = True
        result.file_name = name
        result.file_bytes = data
    except Exception as exc:  # noqa: BLE001
        result.error = f"Could not read the file: {exc}"
    return result


def reset() -> None:
    """Drop the link cache (test helper / teardown)."""
    _links.clear()
