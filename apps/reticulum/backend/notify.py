"""POST a one-line push when an LXMF direct message arrives.

Points at an [ntfy](https://ntfy.sh) topic (`https://ntfy.sh/my-topic`, or a
self-hosted server) or any webhook that accepts a plain-text POST body: the
message text is the body, the sender is an ntfy-style ``Title`` header.
Fire-and-forget from the inbound handler; stdlib ``urllib`` only, run off
the event loop.
"""

from __future__ import annotations

import logging
import urllib.request

from . import http

logger = logging.getLogger(__name__)

_TIMEOUT_S = 8
_MAX_BODY = 3072


def post(url: str, *, title: str, body: str) -> bool:
    """POST *body* to *url* with an ntfy-style ``Title`` header. Returns
    ``True`` on a 2xx response, ``False`` on anything else. Never raises."""
    if not url:
        return False
    try:
        req = urllib.request.Request(
            url,
            data=(body or "(no text)").encode("utf-8")[:_MAX_BODY],
            method="POST",
            headers={
                "User-Agent": "Meshpoint-NomadNet-node",
                "Title": _header_safe(title) or "Meshpoint",
                "Tags": "envelope",
            },
        )
        with http.open_request(req, timeout=_TIMEOUT_S) as resp:
            return 200 <= getattr(resp, "status", 200) < 300
    except Exception:  # noqa: BLE001 -- any failure is non-fatal, just log it
        logger.debug("notify request failed")
        return False


def _header_safe(s: str) -> str:
    """HTTP header values must be latin-1 and single-line; ntfy titles are
    plain text. Drop anything non-ASCII/non-printable and cap the length."""
    return "".join(
        c for c in (s or "") if c.isprintable() and ord(c) < 128
    ).strip()[:96]
