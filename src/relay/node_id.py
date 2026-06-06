"""Normalize and validate Meshtastic node IDs for relay filter lists."""

from __future__ import annotations

import re

_NODE_ID_RE = re.compile(r"^[0-9a-f]{8}$", re.IGNORECASE)


def normalize_node_id(node_id: str) -> str:
    """Strip optional ``!`` prefix and lowercase for consistent matching."""
    return (node_id or "").strip().lower().lstrip("!")


def validate_node_ids(node_ids: list[str]) -> list[str]:
    """Return normalized unique node IDs or raise ValueError."""
    seen: set[str] = set()
    normalized: list[str] = []
    for raw in node_ids:
        nid = normalize_node_id(raw)
        if not _NODE_ID_RE.match(nid):
            raise ValueError(
                f"Invalid node ID {raw!r} — expected 8 hex chars (no ! prefix)"
            )
        if nid not in seen:
            seen.add(nid)
            normalized.append(nid)
    return normalized
