"""IPC protocol between MeshtasticdBridgeSource and the bridge worker."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

FATAL_PREFIX = "__fatal__:"


class BridgeCommand(str, Enum):
    STOP = "stop"
    SEND_TEXT = "send_text"
    SEND_NODEINFO = "send_nodeinfo"
    READ_RADIO_STATE = "read_radio_state"
    WRITE_LORA = "write_lora"
    WRITE_OWNER = "write_owner"


class BridgeResponse(str, Enum):
    READY = "ready"
    OK = "ok"
    ERROR = "error"


@dataclass(frozen=True)
class BridgeSendTextRequest:
    text: str
    destination: int
    channel: int
    want_ack: bool


@dataclass(frozen=True)
class BridgeSendNodeinfoRequest:
    long_name: str
    short_name: str
    hw_model: int


def fatal_message(reason: str) -> str:
    return f"{FATAL_PREFIX}{reason}"


def is_fatal_message(message: Any) -> bool:
    return isinstance(message, str) and message.startswith(FATAL_PREFIX)


def fatal_reason(message: str) -> str:
    return message[len(FATAL_PREFIX) :]
