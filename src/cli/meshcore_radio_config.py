"""MeshCore companion radio configuration helpers.

Provides region presets and serial-based radio configuration for the
setup wizard.  Uses the ``meshcore`` Python library to query and set
RF parameters on a USB companion over serial.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RadioPreset:
    label: str
    frequency_mhz: float
    bandwidth_khz: float
    spreading_factor: int
    coding_rate: int


REGION_PRESETS: dict[str, RadioPreset] = {
    "US": RadioPreset("US  (910.525 MHz / BW62.5 / SF7 / CR5)", 910.525, 62.5, 7, 5),
    "EU": RadioPreset("EU  (869.525 MHz / BW62.5 / SF7 / CR5)", 869.525, 62.5, 7, 5),
    "ANZ": RadioPreset("ANZ (915.525 MHz / BW62.5 / SF7 / CR5)", 915.525, 62.5, 7, 5),
}

_REBOOT_WAIT_SECONDS = 4


@dataclass
class RadioStatus:
    frequency_mhz: float = 0.0
    bandwidth_khz: float = 0.0
    spreading_factor: int = 0
    coding_rate: int = 0
    name: str = ""
    tx_power: int = 0
    model: str = ""

    def summary(self) -> str:
        return (
            f"{self.frequency_mhz} MHz / BW{self.bandwidth_khz} "
            f"/ SF{self.spreading_factor} / CR{self.coding_rate}"
        )


async def _query_async(port: str, baud: int) -> Optional[RadioStatus]:
    """Connect briefly to read current radio settings via SELF_INFO."""
    try:
        from meshcore import MeshCore

        mc = await MeshCore.create_serial(port, baud)
        info = mc.self_info or {}

        device_info = await mc.commands.send_device_query()
        model = ""
        if device_info and hasattr(device_info, "payload"):
            model = device_info.payload.get("model", "")

        await mc.disconnect()

        if not info.get("radio_freq"):
            return None

        return RadioStatus(
            frequency_mhz=float(info.get("radio_freq", 0)),
            bandwidth_khz=float(info.get("radio_bw", 0)),
            spreading_factor=int(info.get("radio_sf", 0)),
            coding_rate=int(info.get("radio_cr", 0)),
            name=info.get("name", ""),
            tx_power=int(info.get("tx_power", 0)),
            model=model,
        )
    except Exception:
        logger.debug("Failed to query MeshCore radio on %s", port, exc_info=True)
        return None


async def _configure_async(
    port: str,
    baud: int,
    freq: float,
    bw: float,
    sf: int,
    cr: int,
) -> bool:
    """Set radio parameters and reboot the companion."""
    try:
        from meshcore import MeshCore, EventType

        mc = await MeshCore.create_serial(port, baud)
        result = await mc.commands.set_radio(freq, bw, sf, cr)

        if hasattr(result, "type") and result.type == EventType.ERROR:
            await mc.disconnect()
            return False

        await mc.commands.reboot()
        await mc.disconnect()
        return True
    except Exception:
        logger.debug("Failed to configure MeshCore radio on %s", port, exc_info=True)
        return False


async def _verify_async(port: str, baud: int) -> Optional[RadioStatus]:
    """Reconnect after reboot and read back settings."""
    return await _query_async(port, baud)


def query_radio(port: str, baud: int = 115200) -> Optional[RadioStatus]:
    """Synchronous wrapper for querying current radio settings."""
    return asyncio.run(_query_async(port, baud))


def configure_radio(
    port: str,
    freq: float,
    bw: float,
    sf: int,
    cr: int,
    baud: int = 115200,
) -> bool:
    """Synchronous wrapper for setting radio + reboot."""
    return asyncio.run(_configure_async(port, baud, freq, bw, sf, cr))


def verify_radio(port: str, baud: int = 115200) -> Optional[RadioStatus]:
    """Synchronous wrapper for post-reboot verification."""
    return asyncio.run(_verify_async(port, baud))
