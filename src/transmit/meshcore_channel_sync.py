"""Sync MeshCore companion channel slots from local config.

Slot 0 stays Public. User keys write to slots 1..N so device
``channel_idx`` matches the Messages tab.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

# Slot 0 = Public (firmware default). User keys use slots 1..N.
MESHCORE_PUBLIC_SLOT_INDEX = 0
MESHCORE_MAX_DEVICE_SLOTS = 8
MESHCORE_MAX_USER_CHANNELS = MESHCORE_MAX_DEVICE_SLOTS - 1



class MeshcoreChannelSync:
    """Writes configured channel keys onto a live MeshCore connection."""

    def __init__(
        self,
        meshcore: Any,
        post_command: Optional[Callable[[], Any]] = None,
    ) -> None:
        self._mc = meshcore
        self._post_command = post_command

    async def sync(self, channel_keys: dict) -> None:
        """Probe device slots, then set or clear user slots as needed."""
        try:
            from meshcore import EventType
        except ImportError:
            logger.warning("sync_channels: meshcore library unavailable")
            return

        max_slots = MESHCORE_MAX_DEVICE_SLOTS
        device_slots = await self._probe_slots(EventType, max_slots)
        desired = list(channel_keys.items())
        if len(desired) > MESHCORE_MAX_USER_CHANNELS:
            logger.warning(
                "sync_channels: more than %d user channels configured, "
                "ignoring extras",
                MESHCORE_MAX_USER_CHANNELS,
            )
            desired = desired[:MESHCORE_MAX_USER_CHANNELS]

        await self._write_desired(desired, device_slots)
        await self._clear_extras(1 + len(desired), max_slots, device_slots)

        if self._post_command:
            await self._post_command()
        logger.info("sync_channels: done (%d configured)", len(desired))

    async def _probe_slots(
        self, event_type_cls: Any, max_slots: int
    ) -> dict[int, tuple[str, bytes]]:
        device_slots: dict[int, tuple[str, bytes]] = {}
        for i in range(max_slots):
            try:
                result = await asyncio.wait_for(
                    self._mc.commands.get_channel(i), timeout=5.0
                )
            except asyncio.TimeoutError:
                logger.warning(
                    "sync_channels: timeout reading slot %d, stopping probe",
                    i,
                )
                break
            except Exception:
                logger.exception(
                    "sync_channels: error reading slot %d", i
                )
                break
            if result.type == event_type_cls.ERROR:
                break
            payload = result.payload
            device_slots[i] = (
                payload.get("channel_name", ""),
                payload.get("channel_secret", b""),
            )
        return device_slots

    async def verify(self, channel_keys: dict) -> None:
        """Require readback of every configured and cleared slot before a UI save succeeds."""
        from meshcore import EventType

        slots = await self._probe_slots(EventType, MESHCORE_MAX_DEVICE_SLOTS)
        if len(channel_keys) > MESHCORE_MAX_USER_CHANNELS:
            raise ValueError('Too many MeshCore channels')
        desired = list(channel_keys.items())
        for index in range(1, MESHCORE_MAX_DEVICE_SLOTS):
            if index not in slots:
                raise RuntimeError('MeshCore channel readback incomplete')
            name, secret = slots[index]
            if index <= len(desired):
                expected_name, expected_key = desired[index - 1]
                if name != expected_name or secret != bytes.fromhex(expected_key):
                    raise RuntimeError('MeshCore channel readback did not match')
            elif name:
                raise RuntimeError('MeshCore channel deletion did not persist')

    async def _write_desired(
        self,
        desired: list[tuple[str, str]],
        device_slots: dict[int, tuple[str, bytes]],
    ) -> None:
        for user_idx, (name, key_hex) in enumerate(desired):
            slot = user_idx + 1
            try:
                secret = bytes.fromhex(key_hex)
            except ValueError:
                logger.warning(
                    "sync_channels: invalid hex key for '%s', skipping",
                    name,
                )
                continue
            if len(secret) != 16:
                logger.warning(
                    "sync_channels: key for '%s' must be 16 bytes, skipping",
                    name,
                )
                continue
            dev_name, dev_secret = device_slots.get(slot, ("", b""))
            if dev_name == name and dev_secret == secret:
                logger.debug(
                    "sync_channels: slot %d already correct (%s)",
                    slot,
                    name,
                )
                continue
            try:
                await asyncio.wait_for(
                    self._mc.commands.set_channel(slot, name, secret),
                    timeout=5.0,
                )
                logger.info("sync_channels: set slot %d → %s", slot, name)
            except Exception:
                logger.exception(
                    "sync_channels: failed to set slot %d (%s)",
                    slot,
                    name,
                )

    async def _clear_extras(
        self,
        first_clear: int,
        max_slots: int,
        device_slots: dict[int, tuple[str, bytes]],
    ) -> None:
        for idx in range(first_clear, max_slots):
            dev = device_slots.get(idx)
            if dev is None:
                break
            dev_name, _ = dev
            if not dev_name:
                continue
            try:
                await asyncio.wait_for(
                    self._mc.commands.set_channel(idx, "", b"\x00" * 16),
                    timeout=5.0,
                )
                logger.info("sync_channels: cleared slot %d", idx)
            except Exception:
                logger.exception(
                    "sync_channels: failed to clear slot %d", idx
                )
