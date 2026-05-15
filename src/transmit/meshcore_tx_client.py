"""MeshCore message transmission via USB or TCP companion.

Wraps the meshcore Python library for outbound messaging. Shares
the existing MeshCore connection from MeshcoreUsbCaptureSource
to avoid opening a second serial connection to the same port.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class SendResult:
    """Outcome of a MeshCore send attempt."""

    success: bool
    event_type: str = ""
    error: str = ""


@dataclass
class RadioStatus:
    """MeshCore companion radio parameters."""

    frequency_mhz: float = 0.0
    bandwidth_khz: float = 0.0
    spreading_factor: int = 0
    coding_rate: int = 0
    tx_power: int = 0
    name: str = ""


class MeshCoreTxClient:
    """Sends messages through a MeshCore companion node.

    Designed to share the MeshCore connection already held by
    MeshcoreUsbCaptureSource. Use set_source() so the client always
    reads the source's *current* MeshCore instance: the capture source
    rebuilds it on every reconnect, and snapshotting the reference
    once at startup leaves the TX client stuck on a dead handle.
    """

    def __init__(self):
        self._owned_mc = None
        self._owned_connected = False
        self._source = None
        self._post_command_callback = None

    @property
    def _mc(self):
        """Live MeshCore handle. Prefers the shared source if attached."""
        if self._source is not None:
            return getattr(self._source, "_meshcore", None)
        return self._owned_mc

    @property
    def connected(self) -> bool:
        if self._source is not None:
            return (
                bool(getattr(self._source, "_connected", False))
                and self._mc is not None
            )
        return self._owned_connected and self._owned_mc is not None

    def set_source(self, source) -> None:
        """Attach the capture source so we always see live connect state."""
        self._source = source
        logger.info("MeshCore TX client bound to live capture source")

    def set_connection(self, mc_instance) -> None:
        """Legacy one-shot attach. Prefer set_source() for live state."""
        self._source = None
        self._owned_mc = mc_instance
        self._owned_connected = mc_instance is not None
        if self._owned_connected:
            logger.info("MeshCore TX client attached to shared connection")

    def set_post_command_callback(self, callback) -> None:
        """Register a coroutine to run after each command completes.

        Used to restart auto_message_fetching on the USB source after
        TX operations that may disrupt the event subscription loop.
        """
        self._post_command_callback = callback

    async def _run_post_command(self) -> None:
        if self._post_command_callback:
            try:
                await self._post_command_callback()
            except Exception:
                logger.debug("Post-command callback failed", exc_info=True)

    async def create_connection(
        self,
        port: str,
        baud_rate: int = 115200,
        connection_type: str = "serial",
        tcp_host: str = "",
        tcp_port: int = 0,
    ) -> bool:
        """Create a standalone connection (only if no shared one exists)."""
        if self.connected:
            return True
        try:
            from meshcore import MeshCore

            if connection_type == "tcp" and tcp_host:
                self._owned_mc = await MeshCore.create_tcp(tcp_host, tcp_port)
            else:
                self._owned_mc = await MeshCore.create_serial(port, baud_rate)
            if self._owned_mc is None:
                logger.error(
                    "MeshCore TX client handshake failed on %s "
                    "(meshcore returned None)",
                    port,
                )
                self._owned_connected = False
                return False
            self._source = None
            self._owned_connected = True
            logger.info("MeshCore TX client connected (%s)", connection_type)
            return True
        except Exception:
            logger.exception("MeshCore TX client connection failed")
            self._owned_connected = False
            return False

    async def send_channel_message(
        self, channel: int, text: str
    ) -> SendResult:
        """Send a broadcast message on a MeshCore channel."""
        if not self.connected:
            return SendResult(success=False, error="Not connected")
        try:
            result = await asyncio.wait_for(
                self._mc.commands.send_chan_msg(channel, text),
                timeout=10.0,
            )
            event_type = (
                result.type.value
                if hasattr(result.type, "value")
                else str(result.type)
            )
            logger.info(
                "MeshCore channel %d message sent: %s", channel, event_type
            )
            await self._run_post_command()
            return SendResult(success=True, event_type=event_type)
        except asyncio.TimeoutError:
            await self._run_post_command()
            return SendResult(success=False, error="Send timed out")
        except Exception as exc:
            logger.exception("MeshCore channel send failed")
            await self._run_post_command()
            return SendResult(success=False, error=str(exc))

    async def send_direct_message(
        self, destination, text: str
    ) -> SendResult:
        """Send a direct message to a MeshCore contact."""
        if not self.connected:
            return SendResult(success=False, error="Not connected")
        try:
            result = await asyncio.wait_for(
                self._mc.commands.send_msg(destination, text),
                timeout=10.0,
            )
            event_type = (
                result.type.value
                if hasattr(result.type, "value")
                else str(result.type)
            )
            logger.info("MeshCore DM sent: %s", event_type)
            await self._run_post_command()
            return SendResult(success=True, event_type=event_type)
        except asyncio.TimeoutError:
            await self._run_post_command()
            return SendResult(success=False, error="Send timed out")
        except Exception as exc:
            logger.exception("MeshCore DM send failed")
            await self._run_post_command()
            return SendResult(success=False, error=str(exc))

    async def send_advert(self, flood: bool = False) -> SendResult:
        """Broadcast a node advertisement."""
        if not self.connected:
            return SendResult(success=False, error="Not connected")
        try:
            result = await asyncio.wait_for(
                self._mc.commands.send_advert(flood=flood),
                timeout=10.0,
            )
            event_type = (
                result.type.value
                if hasattr(result.type, "value")
                else str(result.type)
            )
            logger.info("MeshCore advert sent: %s", event_type)
            await self._run_post_command()
            return SendResult(success=True, event_type=event_type)
        except asyncio.TimeoutError:
            await self._run_post_command()
            return SendResult(success=False, error="Advert timed out")
        except Exception as exc:
            logger.exception("MeshCore advert send failed")
            await self._run_post_command()
            return SendResult(success=False, error=str(exc))

    @staticmethod
    def _normalize_contact_payload(payload) -> list[dict]:
        """Accept both dict-keyed-by-pubkey and list formats."""
        if isinstance(payload, dict):
            return list(payload.values())
        if isinstance(payload, list):
            return [e for e in payload if isinstance(e, dict)]
        return []

    async def get_radio_info(self) -> Optional[RadioStatus]:
        """Read companion radio parameters from the cached SELF_INFO frame.

        SELF_INFO is captured during the handshake and is the authoritative
        source for radio_freq / radio_bw / radio_sf / radio_cr / tx_power /
        name. send_device_query() does not return those fields, so reading
        from there left the dashboard stuck on Unknown / ?.
        """
        if not self.connected:
            return None
        try:
            info = self._mc.self_info or {}
            if not info:
                return None
            return RadioStatus(
                frequency_mhz=float(info.get("radio_freq", 0.0)),
                bandwidth_khz=float(info.get("radio_bw", 0.0)),
                spreading_factor=int(info.get("radio_sf", 0)),
                coding_rate=int(info.get("radio_cr", 0)),
                tx_power=int(info.get("tx_power", 0)),
                name=info.get("name", ""),
            )
        except Exception:
            logger.exception("Failed to read MeshCore radio info")
            return None

    async def sync_channels(self, channel_keys: dict) -> None:
        """Sync configured channels to the companion device.

        Writes each channel from channel_keys to a numbered slot (0, 1, …),
        then clears any slots beyond that count that still hold a name on the
        device. channel_keys maps channel name → hex-encoded 16-byte secret.
        """
        if not self.connected:
            logger.debug("sync_channels: not connected, skipping")
            return
        try:
            from meshcore import EventType
        except ImportError:
            logger.warning("sync_channels: meshcore library unavailable")
            return

        _MAX_SLOTS = 8

        # Read current device slots.
        device_slots: dict[int, tuple[str, bytes]] = {}
        for i in range(_MAX_SLOTS):
            try:
                result = await asyncio.wait_for(
                    self._mc.commands.get_channel(i), timeout=5.0
                )
            except asyncio.TimeoutError:
                logger.warning("sync_channels: timeout reading slot %d, stopping probe", i)
                break
            except Exception:
                logger.exception("sync_channels: error reading slot %d", i)
                break
            if result.type == EventType.ERROR:
                break
            p = result.payload
            device_slots[i] = (
                p.get("channel_name", ""),
                p.get("channel_secret", b""),
            )

        desired = list(channel_keys.items())  # [(name, key_hex), …]

        # Write desired channels.
        for idx, (name, key_hex) in enumerate(desired):
            if idx >= _MAX_SLOTS:
                logger.warning("sync_channels: more than %d channels configured, ignoring extras", _MAX_SLOTS)
                break
            try:
                secret = bytes.fromhex(key_hex)
            except ValueError:
                logger.warning("sync_channels: invalid hex key for '%s', skipping", name)
                continue
            dev_name, dev_secret = device_slots.get(idx, ("", b""))
            if dev_name == name and dev_secret == secret:
                logger.debug("sync_channels: slot %d already correct (%s)", idx, name)
                continue
            try:
                await asyncio.wait_for(
                    self._mc.commands.set_channel(idx, name, secret), timeout=5.0
                )
                logger.info("sync_channels: set slot %d → %s", idx, name)
            except Exception:
                logger.exception("sync_channels: failed to set slot %d (%s)", idx, name)

        # Clear any extra populated slots on the device.
        for idx in range(len(desired), _MAX_SLOTS):
            dev = device_slots.get(idx)
            if dev is None:
                break
            dev_name, _ = dev
            if not dev_name:
                continue
            try:
                await asyncio.wait_for(
                    self._mc.commands.set_channel(idx, "", b"\x00" * 16), timeout=5.0
                )
                logger.info("sync_channels: cleared slot %d", idx)
            except Exception:
                logger.exception("sync_channels: failed to clear slot %d", idx)

        await self._run_post_command()
        logger.info("sync_channels: done (%d configured)", len(desired))

    async def get_contacts(self) -> list[dict]:
        """Retrieve the companion's contact list."""
        if not self.connected:
            return []
        try:
            result = await asyncio.wait_for(
                self._mc.commands.get_contacts(),
                timeout=10.0,
            )
            entries = self._normalize_contact_payload(result.payload)
            contacts = []
            for i, entry in enumerate(entries):
                name = (
                    entry.get("adv_name")
                    or entry.get("name")
                    or ""
                )
                pk = entry.get("public_key", "")
                if name and pk:
                    contacts.append({
                        "index": i,
                        "name": name,
                        "public_key": pk,
                        "last_seen": entry.get("lastmod", 0),
                    })
            logger.info("get_contacts: %d contacts parsed", len(contacts))
            return contacts
        except Exception:
            logger.exception("Failed to retrieve MeshCore contacts")
            return []
