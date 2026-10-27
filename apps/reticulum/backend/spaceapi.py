"""Fetch a hackerspace's SpaceAPI status for the hosted node's
``/page/spacestate.mu``.

SpaceAPI (https://spaceapi.io) is a tiny open JSON standard every
hackerspace can publish: is the space open, where it is, how to reach it.
This reads one endpoint, normalises the handful of fields that moved
between schema versions (0.13 keeps a top-level ``open``; 13/14/15 nest
everything under ``state``), and hands back a flat dict. The route layer
does the caching -- this just does one HTTP GET.

FastAPI-free; stdlib ``urllib`` only.
"""

from __future__ import annotations

import json
import logging
import urllib.request

from . import http

logger = logging.getLogger(__name__)

_TIMEOUT_S = 8
_MAX_BYTES = 256 * 1024


def fetch(url: str) -> dict | None:
    """``{space, open, message, lastchange, address, url, irc, email, ml}``
    for the SpaceAPI endpoint at *url*, or ``None`` on any failure. Every
    value can be ``None``/``""`` -- only ``open`` (bool or ``None`` when the
    space doesn't publish a state) really matters."""
    if not url:
        return None
    try:
        req = urllib.request.Request(
            url, headers={"User-Agent": "Meshpoint-NomadNet-node"},
        )
        with http.open_request(req, timeout=_TIMEOUT_S) as resp:
            raw = resp.read(_MAX_BYTES + 1)
        if len(raw) > _MAX_BYTES:
            raise ValueError("SpaceAPI response too large")
        data = json.loads(raw.decode("utf-8", errors="replace"))
    except Exception:  # noqa: BLE001 -- any failure -> None, page shows "unknown"
        logger.debug("spaceapi request failed")
        return None
    if not isinstance(data, dict):
        return None

    state = data.get("state") if isinstance(data.get("state"), dict) else {}
    location = data.get("location") if isinstance(data.get("location"), dict) else {}
    contact = data.get("contact") if isinstance(data.get("contact"), dict) else {}

    open_val = state.get("open")
    if open_val is None:
        open_val = data.get("open")  # 0.13 top-level
    lastchange = state.get("lastchange") or data.get("lastchange")

    return {
        "space": _s(data.get("space")),
        "open": open_val if isinstance(open_val, bool) else None,
        "message": _s(state.get("message")),
        "lastchange": int(lastchange) if isinstance(lastchange, (int, float)) else None,
        "address": _s(location.get("address")),
        "url": _s(data.get("url")),
        "irc": _s(contact.get("irc")),
        "email": _deobfuscate(_s(contact.get("email"))),
        "ml": _s(contact.get("ml")),
    }


def _s(v) -> str:
    return v.strip() if isinstance(v, str) else ""


def _deobfuscate(email: str) -> str:
    """`hack AT techinc DOT nl` -> `hack@techinc.nl` (a common SpaceAPI
    anti-scrape dodge); leave a normal address untouched."""
    if "@" in email or not email:
        return email
    return (
        email.replace(" AT ", "@").replace(" at ", "@")
        .replace(" DOT ", ".").replace(" dot ", ".")
    )
