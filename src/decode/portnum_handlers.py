"""Meshtastic portnum payload decoders.

This is a stub module. The compiled core module (.so) overrides this
at runtime when meshpoint-core is installed.
"""

from __future__ import annotations

from typing import Any, Optional

from src.models.packet import PacketType


def dispatch_portnum(
    portnum: int, payload: bytes
) -> tuple[Optional[dict[str, Any]], PacketType]:
    raise RuntimeError(
        "portnum_handlers requires meshpoint-core. "
        "See docs/ONBOARDING.md for installation."
    )
