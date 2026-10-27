"""Channel configuration owned by the native Meshtastic node."""

from __future__ import annotations

import base64
import binascii


def read_channels(node):
    return [
        {
            "index": ch.index,
            "name": ch.settings.name,
            "psk_b64": base64.b64encode(ch.settings.psk).decode(),
            "enabled": bool(ch.role),
            "hash": "",
        }
        for ch in node.channels
        if ch.role or ch.index == 0 or ch.settings.name
    ]


def write_channels(node, channels):
    """Validate the entire update before writing any node settings."""
    from meshtastic.protobuf import channel_pb2

    if not 1 <= len(channels) <= 8:
        raise ValueError(
            "Provide a primary channel and at most seven secondary channels"
        )
    indices = [ch["index"] for ch in channels]
    if (
        len(set(indices)) != len(indices)
        or 0 not in indices
        or any(i < 0 or i > 7 for i in indices)
    ):
        raise ValueError(
            "Channel indices must be unique, between 0 and 7, and include 0"
        )
    prepared = {}
    for entry in channels:
        index = entry["index"]
        name = entry.get("name", "")
        if len(name.encode("utf-8")) > 11:
            raise ValueError("Meshtastic channel names must fit in 11 UTF-8 bytes")
        try:
            key = base64.b64decode(entry.get("psk_b64", ""), validate=True)
        except (ValueError, binascii.Error) as exc:
            raise ValueError("Invalid channel key encoding") from exc
        if len(key) not in (0, 1, 16, 32):
            raise ValueError("Meshtastic keys must contain 0, 1, 16, or 32 bytes")
        ch = channel_pb2.Channel()
        existing = node.getChannelByChannelIndex(index)
        if existing is not None:
            ch.CopyFrom(existing)
        ch.index = index
        ch.settings.name = name
        ch.settings.psk = key
        ch.role = 1 if index == 0 else (2 if entry.get("enabled", True) else 0)
        prepared[index] = ch
    for index in range(8):
        current = node.getChannelByChannelIndex(index)
        replacement = prepared.get(index)
        if replacement is None:
            if current is None or not current.role:
                continue
            replacement = channel_pb2.Channel(index=index, role=0)
        if current == replacement:
            continue
        node.channels[index].CopyFrom(replacement)
        node.writeChannel(index)
    return read_channels(node)
