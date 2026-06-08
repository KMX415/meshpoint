"""Decode Meshtastic ADMIN responses into JSON-safe, redacted dicts."""
from __future__ import annotations

import re
from typing import Any

from google.protobuf.json_format import MessageToDict
from google.protobuf.message import Message

_SENSITIVE_RE = re.compile(
    r"(psk|private_key|public_key|admin_key|session_passkey|passkey|key)$",
    re.IGNORECASE,
)


def message_to_redacted_dict(msg: Message) -> dict[str, Any]:
    """Convert a protobuf message to a dict with secrets redacted."""
    raw = MessageToDict(msg, preserving_proto_field_name=True)
    return _redact_value(raw)


def _redact_value(value: Any, key: str | None = None) -> Any:
    if key and _SENSITIVE_RE.search(key):
        return "***"
    if isinstance(value, dict):
        return {k: _redact_value(v, k) for k, v in value.items()}
    if isinstance(value, list):
        return [_redact_value(item) for item in value]
    return value
