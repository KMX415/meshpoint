"""Resolve which Meshtastic node IDs represent this device for DM routing."""

from __future__ import annotations


def build_our_meshtastic_node_ids(
    configured_node_id: int | None,
    meshtasticd_node_hex: str | None,
) -> frozenset[str]:
    """Node IDs that count as 'us' for DM storage and unread badges."""
    ids: set[str] = set()
    if configured_node_id:
        ids.add(f"{int(configured_node_id):08x}")
    if meshtasticd_node_hex:
        normalized = meshtasticd_node_hex.lower().removeprefix("!")
        if len(normalized) >= 8:
            ids.add(normalized[-8:])
        elif normalized:
            ids.add(normalized.zfill(8))
    return frozenset(ids)
