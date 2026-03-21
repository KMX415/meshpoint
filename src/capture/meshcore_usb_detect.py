"""Auto-detect MeshCore USB devices on serial ports.

Scans /dev/ttyUSB* and /dev/ttyACM* for devices that respond to
MeshCore serial commands.  Used at startup for plug-and-play support
and by the setup wizard for hardware discovery.
"""

from __future__ import annotations

import asyncio
import glob
import logging
from typing import Optional

logger = logging.getLogger(__name__)

_USB_SERIAL_PATTERNS = ["/dev/ttyUSB*", "/dev/ttyACM*"]
_PROBE_TIMEOUT_SECONDS = 5.0


def find_serial_candidates(
    exclude_ports: frozenset[str] = frozenset(),
) -> list[str]:
    """List USB serial ports that could be MeshCore devices."""
    candidates: list[str] = []
    for pattern in _USB_SERIAL_PATTERNS:
        candidates.extend(glob.glob(pattern))
    return sorted(p for p in candidates if p not in exclude_ports)


async def probe_meshcore_device(
    port: str,
    baud: int = 115200,
    timeout: float = _PROBE_TIMEOUT_SECONDS,
) -> bool:
    """Connect to *port* and verify it responds as a MeshCore device."""
    try:
        from meshcore import MeshCore, EventType

        mc = await asyncio.wait_for(
            MeshCore.create_serial(port, baud),
            timeout=timeout,
        )
        result = await asyncio.wait_for(
            mc.commands.send_device_query(),
            timeout=timeout,
        )
        await mc.disconnect()
        return result.type != EventType.ERROR
    except Exception:
        logger.debug("Port %s is not a MeshCore device", port, exc_info=True)
        return False


async def detect_meshcore_port(
    exclude_ports: frozenset[str] = frozenset(),
    baud: int = 115200,
) -> Optional[str]:
    """Return the first USB serial port with a responding MeshCore device."""
    candidates = find_serial_candidates(exclude_ports)
    if not candidates:
        return None

    for port in candidates:
        logger.debug("Probing %s for MeshCore device...", port)
        if await probe_meshcore_device(port, baud):
            logger.info("MeshCore device detected on %s", port)
            return port

    return None
