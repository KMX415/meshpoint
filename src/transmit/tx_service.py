"""Unified message transmission service for Meshtastic and MeshCore.

Routes outbound messages to the appropriate TX path: native SX1261
for Meshtastic, USB/TCP companion for MeshCore.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import random
import secrets
import time
from dataclasses import dataclass
from typing import Optional

from src.models.packet import Protocol
from src.transmit.duty_cycle import DutyCycleTracker
from src.transmit.reply_hop_policy import MeshtasticReplyHopPolicy

logger = logging.getLogger(__name__)

BROADCAST_ADDR_MT = 0xFFFFFFFF
BROADCAST_ADDR_MC = 0xFFFF

RESERVED_NODE_IDS: frozenset[int] = frozenset({0x00000000, 0xFFFFFFFF})

PORTNUM_NODEINFO = 4
HW_MODEL_PRIVATE_HW = 255
HW_MODEL_PORTDUINO = 37
DEFAULT_HOP_LIMIT = 3

PRESET_DISPLAY_NAMES: dict[tuple[int, int], str] = {
    (7, 250): "ShortFast",
    (7, 500): "ShortTurbo",
    (8, 250): "ShortSlow",
    (9, 250): "MediumFast",
    (10, 250): "MediumSlow",
    (11, 250): "LongFast",
    (11, 500): "LongTurbo",
    (11, 125): "LongMod",
    (12, 125): "LongSlow",
    (12, 62): "VLongSlow",
}


@dataclass
class SendResult:
    """Outcome of a transmission attempt."""

    success: bool
    packet_id: str = ""
    protocol: str = ""
    timestamp: float = 0.0
    error: str = ""
    airtime_ms: int = 0


class TxService:
    """Orchestrates message sending across Meshtastic and MeshCore."""

    def __init__(
        self,
        wrapper=None,
        crypto=None,
        channel_plan=None,
        transmit_config=None,
        meshcore_tx=None,
        duty_tracker: Optional[DutyCycleTracker] = None,
        radio_config=None,
        primary_channel_name: str = "",
        device_id: Optional[str] = None,
        persist_derived_node_id: bool = True,
    ):
        self._wrapper = wrapper
        self._crypto = crypto
        self._channel_plan = channel_plan
        self._config = transmit_config
        self._meshcore_tx = meshcore_tx
        self._duty = duty_tracker
        self._radio_config = radio_config
        self._primary_channel_name = primary_channel_name
        self._device_id = device_id
        self._builder = None
        self._packet_counter = random.randint(1, 0xFFFF)
        self._node_id_source: str = "random"
        self._source_node_id = self._resolve_node_id()
        if persist_derived_node_id:
            self._persist_derived_node_id_if_needed()
        self._device_metrics_provider = None
        self._local_stats_provider = None

    @property
    def meshtastic_enabled(self) -> bool:
        return (
            self._config is not None
            and self._config.enabled
            and self._wrapper is not None
        )

    @property
    def meshcore_enabled(self) -> bool:
        return self._meshcore_tx is not None and self._meshcore_tx.connected

    @property
    def source_node_id(self) -> int:
        return self._source_node_id

    def set_telemetry_reply_providers(
        self,
        device_metrics_provider=None,
        local_stats_provider=None,
    ) -> None:
        self._device_metrics_provider = device_metrics_provider
        self._local_stats_provider = local_stats_provider

    @staticmethod
    def _recipient_pubkey_for_reply(original, requester: int, crypto) -> bytes | None:
        """Use PKI only when the inbound request was PKI-encrypted (ch=0x00)."""
        if original.channel_hash != 0:
            return None
        if crypto is None:
            return None
        key = crypto.lookup_public_key(requester)
        if key is None:
            key = crypto.refresh_public_key_from_db(requester)
        return key

    @staticmethod
    def _reply_hop_fields(original, configured_hop_limit: int) -> tuple[int, int]:
        """Mirror firmware hop limits for want_response replies."""
        return MeshtasticReplyHopPolicy.reply_hop_fields(
            original.hop_limit,
            original.hop_start,
            configured_hop_limit,
        )

    @property
    def node_id_source(self) -> str:
        """Where the resolved node_id came from: 'config', 'derived', or 'random'."""
        return self._node_id_source

    async def send_text(
        self,
        text: str,
        destination: int | str = 0,
        protocol: str = "meshtastic",
        channel: int = 0,
        want_ack: bool = False,
    ) -> SendResult:
        """Send a text message over the specified protocol."""
        if protocol.lower() in ("meshtastic", "mt"):
            return await self._send_meshtastic(
                text, destination, channel, want_ack
            )
        elif protocol.lower() in ("meshcore", "mc"):
            return await self._send_meshcore(text, destination, channel)
        else:
            return SendResult(
                success=False, error=f"Unknown protocol: {protocol}"
            )

    async def send_nodeinfo(
        self,
        long_name: str,
        short_name: str,
        hw_model: int = HW_MODEL_PRIVATE_HW,
    ) -> SendResult:
        """Broadcast a Meshtastic NodeInfo packet announcing this Meshpoint.

        Lets recipient Meshtastic clients form a stable contact entry so
        DMs route to/from the Meshpoint correctly. Uses the same
        ``source_node_id`` as outbound text messages.
        """
        if not self.meshtastic_enabled:
            return SendResult(
                success=False,
                protocol="meshtastic",
                error="Meshtastic TX not available",
            )

        builder = self._get_builder()
        if builder is None or not hasattr(builder, "build_nodeinfo"):
            return SendResult(
                success=False,
                protocol="meshtastic",
                error="NodeInfo builder unavailable",
            )

        packet_id = self._next_packet_id()
        channel_hash, channel_key = self._resolve_channel(0)
        public_key = None
        if self._crypto is not None:
            public_key = self._crypto.public_key

        try:
            nodeinfo_hop_limit = self._config.hop_limit if self._config else DEFAULT_HOP_LIMIT
            packet_bytes = builder.build_nodeinfo(
                source_id=self._source_node_id,
                packet_id=packet_id,
                long_name=long_name,
                short_name=short_name,
                hw_model=hw_model,
                public_key=public_key,
                channel_key=channel_key,
                channel_hash=channel_hash,
                hop_limit=nodeinfo_hop_limit,
                hop_start=nodeinfo_hop_limit,
            )
        except Exception as exc:
            logger.exception("NodeInfo build failed")
            return SendResult(
                success=False,
                protocol="meshtastic",
                packet_id=f"{packet_id:08x}",
                error=f"NodeInfo build failed: {exc}",
            )

        if packet_bytes is None:
            return SendResult(
                success=False,
                protocol="meshtastic",
                packet_id=f"{packet_id:08x}",
                error="NodeInfo packet build returned None",
            )

        logger.info(
            "TX NodeInfo: src=%08x id=%08x long=%r short=%r len=%d",
            self._source_node_id, packet_id, long_name, short_name,
            len(packet_bytes),
        )

        tx_pkt = self._build_hal_packet(packet_bytes)
        airtime_ms = await self._get_airtime(tx_pkt)

        if self._duty and not self._duty.check_budget(airtime_ms):
            return SendResult(
                success=False,
                protocol="meshtastic",
                packet_id=f"{packet_id:08x}",
                error="Duty cycle limit reached",
                airtime_ms=airtime_ms,
            )

        result_code = await asyncio.to_thread(self._wrapper.send, tx_pkt)
        if result_code == 0:
            if self._duty:
                self._duty.record_tx(airtime_ms)
            return SendResult(
                success=True,
                protocol="meshtastic",
                packet_id=f"{packet_id:08x}",
                timestamp=time.time(),
                airtime_ms=airtime_ms,
            )
        return SendResult(
            success=False,
            protocol="meshtastic",
            packet_id=f"{packet_id:08x}",
            error=f"lgw_send returned {result_code}",
        )

    async def _send_meshtastic(
        self,
        text: str,
        destination: int | str,
        channel: int,
        want_ack: bool,
    ) -> SendResult:
        """Build and transmit a Meshtastic packet via the SX1261."""
        if not self.meshtastic_enabled:
            return SendResult(
                success=False,
                protocol="meshtastic",
                error="Meshtastic TX not available",
            )

        builder = self._get_builder()
        if builder is None:
            return SendResult(
                success=False,
                protocol="meshtastic",
                error="Packet builder unavailable",
            )

        dest_int = self._resolve_destination(destination, Protocol.MESHTASTIC)
        packet_id = self._next_packet_id()
        channel_hash, channel_key = self._resolve_channel(channel)
        recipient_pubkey = None
        if dest_int != BROADCAST_ADDR_MT and self._crypto is not None:
            recipient_pubkey = self._crypto.lookup_public_key(dest_int)

        hop_limit = self._config.hop_limit if self._config else DEFAULT_HOP_LIMIT
        packet_bytes = builder.build_text_message(
            text=text,
            dest=dest_int,
            source_id=self._source_node_id,
            packet_id=packet_id,
            channel_key=channel_key,
            channel_hash=channel_hash,
            hop_limit=hop_limit,
            hop_start=hop_limit,
            want_ack=want_ack,
            recipient_public_key=recipient_pubkey,
        )
        if packet_bytes is None:
            return SendResult(
                success=False,
                protocol="meshtastic",
                packet_id=f"{packet_id:08x}",
                error="Packet build failed",
            )

        logger.info(
            "TX packet: dest=%08x src=%08x id=%08x hash=0x%02X len=%d hdr=%s",
            dest_int, self._source_node_id, packet_id, channel_hash,
            len(packet_bytes), packet_bytes[:16].hex(),
        )

        tx_pkt = self._build_hal_packet(packet_bytes)
        airtime_ms = await self._get_airtime(tx_pkt)

        logger.info(
            "TX HAL: freq=%d bw=%d sf=%d cr=%d pow=%d preamble=%d "
            "crc=%s hdr=%s pol=%s size=%d",
            tx_pkt.freq_hz, tx_pkt.bandwidth, tx_pkt.datarate,
            tx_pkt.coderate, tx_pkt.rf_power, tx_pkt.preamble,
            not tx_pkt.no_crc, not tx_pkt.no_header,
            "inv" if tx_pkt.invert_pol else "norm", tx_pkt.size,
        )

        if self._duty and not self._duty.check_budget(airtime_ms):
            return SendResult(
                success=False,
                protocol="meshtastic",
                packet_id=f"{packet_id:08x}",
                error="Duty cycle limit reached",
                airtime_ms=airtime_ms,
            )

        pre_status = await asyncio.to_thread(self._wrapper.get_tx_status, 0)
        logger.info("TX status before send: %d", pre_status)

        result_code = await asyncio.to_thread(self._wrapper.send, tx_pkt)

        if result_code == 0:
            for delay in (0.05, 0.1, 0.5, 1.0):
                await asyncio.sleep(delay)
                st = await asyncio.to_thread(self._wrapper.get_tx_status, 0)
                logger.info("TX status after %.0fms: %d (2=FREE 3=SCHED 4=EMIT)", delay * 1000, st)
                if st == 2:
                    break

            if self._duty:
                self._duty.record_tx(airtime_ms)
            return SendResult(
                success=True,
                protocol="meshtastic",
                packet_id=f"{packet_id:08x}",
                timestamp=time.time(),
                airtime_ms=airtime_ms,
            )
        return SendResult(
            success=False,
            protocol="meshtastic",
            packet_id=f"{packet_id:08x}",
            error=f"lgw_send returned {result_code}",
        )

    async def send_routing_ack(self, original) -> SendResult:
        """Reply with a Meshtastic routing ACK to an inbound DM."""
        if not self.meshtastic_enabled:
            return SendResult(success=False, protocol="meshtastic", error="TX unavailable")

        builder = self._get_builder()
        if builder is None or not hasattr(builder, "build_routing_ack"):
            return SendResult(success=False, protocol="meshtastic", error="Builder unavailable")

        try:
            request_id = int(original.packet_id, 16)
            dest = int(original.source_id, 16)
        except ValueError:
            return SendResult(success=False, protocol="meshtastic", error="Invalid packet ids")

        packet_id = self._next_packet_id()
        channel_hash = original.channel_hash
        _, channel_key = self._resolve_channel_by_hash(channel_hash)
        recipient_pubkey = self._recipient_pubkey_for_reply(
            original, dest, self._crypto
        )
        if channel_hash == 0 and recipient_pubkey is None:
            return SendResult(
                success=False,
                protocol="meshtastic",
                error="No public_key for PKI routing ACK recipient",
            )
        configured = self._config.hop_limit if self._config else DEFAULT_HOP_LIMIT
        hop_limit, hop_start = self._reply_hop_fields(original, configured)

        packet_bytes = builder.build_routing_ack(
            source_id=self._source_node_id,
            dest=dest,
            packet_id=packet_id,
            request_id=request_id,
            channel_key=channel_key,
            channel_hash=channel_hash,
            hop_limit=hop_limit,
            hop_start=hop_start,
            recipient_public_key=recipient_pubkey,
        )
        if packet_bytes is None:
            return SendResult(success=False, protocol="meshtastic", error="ACK build failed")

        return await self._send_built_packet(packet_bytes, packet_id, label="routing ACK")

    async def send_traceroute_reply(self, original) -> SendResult:
        """Reply to a traceroute probe addressed to this node."""
        if not self.meshtastic_enabled:
            return SendResult(success=False, protocol="meshtastic", error="TX unavailable")

        builder = self._get_builder()
        if builder is None or not hasattr(builder, "build_traceroute_reply"):
            return SendResult(success=False, protocol="meshtastic", error="Builder unavailable")

        try:
            requester = int(original.source_id, 16)
            request_id = int(original.packet_id, 16)
        except ValueError:
            return SendResult(success=False, protocol="meshtastic", error="Invalid source id")

        rx_snr = (
            float(original.signal.snr)
            if original.signal and original.signal.snr is not None
            else None
        )
        route_nodes, snr_towards, route_back, snr_back = (
            self._build_traceroute_reply_data(original, rx_snr)
        )

        packet_id = self._next_packet_id()
        channel_hash = original.channel_hash
        _, channel_key = self._resolve_channel_by_hash(channel_hash)
        recipient_pubkey = self._recipient_pubkey_for_reply(
            original, requester, self._crypto
        )
        if channel_hash == 0 and recipient_pubkey is None:
            return SendResult(
                success=False,
                protocol="meshtastic",
                error="No public_key for PKI traceroute reply recipient",
            )
        configured = self._config.hop_limit if self._config else DEFAULT_HOP_LIMIT
        hop_limit, hop_start = self._reply_hop_fields(original, configured)

        packet_bytes = builder.build_traceroute_reply(
            source_id=self._source_node_id,
            dest=requester,
            packet_id=packet_id,
            route_nodes=route_nodes,
            request_id=request_id,
            snr_towards=snr_towards or None,
            route_back=route_back or None,
            snr_back=snr_back or None,
            channel_key=channel_key,
            channel_hash=channel_hash,
            hop_limit=hop_limit,
            hop_start=hop_start,
            recipient_public_key=recipient_pubkey,
        )
        if packet_bytes is None:
            return SendResult(
                success=False, protocol="meshtastic", error="Traceroute build failed"
            )

        return await self._send_built_packet(
            packet_bytes, packet_id, label="traceroute reply"
        )

    async def send_telemetry(
        self,
        *,
        battery_level: int = 101,
        voltage: float = 5.0,
        channel_utilization: float = 0.0,
        air_util_tx: float = 0.0,
        uptime_seconds: int = 0,
    ) -> SendResult:
        if not self.meshtastic_enabled:
            return SendResult(success=False, protocol="meshtastic", error="TX unavailable")

        builder = self._get_builder()
        if builder is None or not hasattr(builder, "build_telemetry"):
            return SendResult(success=False, protocol="meshtastic", error="Builder unavailable")

        packet_id = self._next_packet_id()
        channel_hash, channel_key = self._resolve_channel(0)
        hop_limit = self._config.hop_limit if self._config else DEFAULT_HOP_LIMIT

        packet_bytes = builder.build_telemetry(
            source_id=self._source_node_id,
            packet_id=packet_id,
            battery_level=battery_level,
            voltage=voltage,
            channel_utilization=channel_utilization,
            air_util_tx=air_util_tx,
            uptime_seconds=uptime_seconds,
            channel_key=channel_key,
            channel_hash=channel_hash,
            hop_limit=hop_limit,
            hop_start=hop_limit,
        )
        if packet_bytes is None:
            return SendResult(success=False, protocol="meshtastic", error="Telemetry build failed")

        return await self._send_built_packet(packet_bytes, packet_id, label="telemetry")

    async def send_telemetry_reply(self, original) -> SendResult:
        """Reply to an inbound telemetry request addressed to this node."""
        if not self.meshtastic_enabled:
            return SendResult(success=False, protocol="meshtastic", error="TX unavailable")

        builder = self._get_builder()
        if builder is None or not hasattr(builder, "build_telemetry_reply"):
            return SendResult(success=False, protocol="meshtastic", error="Builder unavailable")

        try:
            requester = int(original.source_id, 16)
            request_id = int(original.packet_id, 16)
        except ValueError:
            return SendResult(success=False, protocol="meshtastic", error="Invalid source id")

        payload = original.decoded_payload or {}
        variant = payload.get("telemetry_variant", "device_metrics")
        if variant == "local_stats":
            metrics = (
                self._local_stats_provider() if self._local_stats_provider else {}
            )
        else:
            metrics = (
                self._device_metrics_provider() if self._device_metrics_provider else {}
            )

        packet_id = self._next_packet_id()
        channel_hash = original.channel_hash
        _, channel_key = self._resolve_channel_by_hash(channel_hash)
        recipient_pubkey = self._recipient_pubkey_for_reply(
            original, requester, self._crypto
        )
        if channel_hash == 0 and recipient_pubkey is None:
            return SendResult(
                success=False,
                protocol="meshtastic",
                error="No public_key for PKI telemetry reply recipient",
            )
        configured = self._config.hop_limit if self._config else DEFAULT_HOP_LIMIT
        hop_limit, hop_start = self._reply_hop_fields(original, configured)

        build_kwargs = {
            "source_id": self._source_node_id,
            "dest": requester,
            "packet_id": packet_id,
            "request_id": request_id,
            "variant": variant,
            "telemetry_time": int(time.time()),
            "channel_key": channel_key,
            "channel_hash": channel_hash,
            "hop_limit": hop_limit,
            "hop_start": hop_start,
            "recipient_public_key": recipient_pubkey,
        }
        if variant == "local_stats":
            build_kwargs.update(
                {
                    "uptime_seconds": int(metrics.get("uptime_seconds", 0)),
                    "channel_utilization": float(
                        metrics.get("channel_utilization", 0.0)
                    ),
                    "air_util_tx": float(metrics.get("air_util_tx", 0.0)),
                    "num_packets_tx": int(metrics.get("num_packets_tx", 0)),
                    "num_packets_rx": int(metrics.get("num_packets_rx", 0)),
                    "num_packets_rx_bad": int(metrics.get("num_packets_rx_bad", 0)),
                    "num_online_nodes": int(metrics.get("num_online_nodes", 0)),
                    "num_total_nodes": int(metrics.get("num_total_nodes", 0)),
                    "num_tx_relay": int(metrics.get("num_tx_relay", 0)),
                }
            )
            noise_floor = metrics.get("noise_floor")
            if noise_floor is not None:
                build_kwargs["noise_floor"] = int(noise_floor)
        else:
            build_kwargs.update(
                {
                    "battery_level": int(metrics.get("battery_level", 101)),
                    "voltage": float(metrics.get("voltage", 5.0)),
                    "channel_utilization": float(
                        metrics.get("channel_utilization", 0.0)
                    ),
                    "air_util_tx": float(metrics.get("air_util_tx", 0.0)),
                    "uptime_seconds": int(metrics.get("uptime_seconds", 0)),
                }
            )

        packet_bytes = builder.build_telemetry_reply(**build_kwargs)
        if packet_bytes is None:
            return SendResult(
                success=False, protocol="meshtastic", error="Telemetry reply build failed"
            )

        return await self._send_built_packet(
            packet_bytes, packet_id, label="telemetry reply"
        )

    async def send_position(
        self,
        latitude: float,
        longitude: float,
        altitude: float | None = None,
    ) -> SendResult:
        if not self.meshtastic_enabled:
            return SendResult(success=False, protocol="meshtastic", error="TX unavailable")

        builder = self._get_builder()
        if builder is None or not hasattr(builder, "build_position"):
            return SendResult(success=False, protocol="meshtastic", error="Builder unavailable")

        packet_id = self._next_packet_id()
        channel_hash, channel_key = self._resolve_channel(0)
        hop_limit = self._config.hop_limit if self._config else DEFAULT_HOP_LIMIT

        packet_bytes = builder.build_position(
            source_id=self._source_node_id,
            packet_id=packet_id,
            latitude=latitude,
            longitude=longitude,
            altitude=altitude,
            channel_key=channel_key,
            channel_hash=channel_hash,
            hop_limit=hop_limit,
            hop_start=hop_limit,
        )
        if packet_bytes is None:
            return SendResult(success=False, protocol="meshtastic", error="Position build failed")

        return await self._send_built_packet(packet_bytes, packet_id, label="position")

    async def _send_built_packet(
        self, packet_bytes: bytes, packet_id: int, *, label: str
    ) -> SendResult:
        tx_pkt = self._build_hal_packet(packet_bytes)
        airtime_ms = await self._get_airtime(tx_pkt)

        if self._duty and not self._duty.check_budget(airtime_ms):
            return SendResult(
                success=False,
                protocol="meshtastic",
                packet_id=f"{packet_id:08x}",
                error="Duty cycle limit reached",
                airtime_ms=airtime_ms,
            )

        result_code = await asyncio.to_thread(self._wrapper.send, tx_pkt)
        if result_code == 0:
            if self._duty:
                self._duty.record_tx(airtime_ms)
            logger.info("TX %s OK: id=%08x airtime=%dms", label, packet_id, airtime_ms)
            return SendResult(
                success=True,
                protocol="meshtastic",
                packet_id=f"{packet_id:08x}",
                timestamp=time.time(),
                airtime_ms=airtime_ms,
            )
        return SendResult(
            success=False,
            protocol="meshtastic",
            packet_id=f"{packet_id:08x}",
            error=f"lgw_send returned {result_code}",
        )

    async def send_raw_relay(
        self, raw_radio_bytes: bytes
    ) -> SendResult:
        """Re-broadcast a captured Meshtastic radio frame verbatim.

        Identity-preserving relay: the original 16-byte radio header
        (source_id, packet_id, channel_hash, …) and encrypted body
        are kept intact. Only ``hop_limit`` (bits 0-2 of the flags
        byte at offset 12) is decremented. Other Meshtastic nodes
        recognise the frame as a relay and apply their own dedup,
        rather than seeing a fresh broadcast originated by this
        Meshpoint.

        Used by RelayManager when the onboard SX1302 is available;
        replaces the legacy USB-companion ``MeshtasticTransmitter``
        path which had to rewrite the source identity.
        """
        if not self.meshtastic_enabled:
            return SendResult(
                success=False,
                protocol="meshtastic",
                error="Meshtastic TX not available",
            )

        if len(raw_radio_bytes) < 16:
            return SendResult(
                success=False,
                protocol="meshtastic",
                error="Packet too short (need full 16-byte header)",
            )

        flags = raw_radio_bytes[12]
        hop_limit = flags & 0x07
        if hop_limit == 0:
            return SendResult(
                success=False,
                protocol="meshtastic",
                error="Packet has no hops remaining",
            )

        new_flags = (flags & ~0x07) | (hop_limit - 1)
        new_packet = bytearray(raw_radio_bytes)
        new_packet[12] = new_flags
        new_packet_bytes = bytes(new_packet)

        tx_pkt = self._build_hal_packet(new_packet_bytes)
        airtime_ms = await self._get_airtime(tx_pkt)

        if self._duty and not self._duty.check_budget(airtime_ms):
            return SendResult(
                success=False,
                protocol="meshtastic",
                error="Duty cycle limit reached",
                airtime_ms=airtime_ms,
            )

        logger.info(
            "Relay TX (native): hops %d -> %d, size=%d, airtime=%dms",
            hop_limit, hop_limit - 1, len(new_packet_bytes), airtime_ms,
        )

        result_code = await asyncio.to_thread(
            self._wrapper.send, tx_pkt
        )
        if result_code == 0:
            if self._duty:
                self._duty.record_tx(airtime_ms)
            return SendResult(
                success=True,
                protocol="meshtastic",
                timestamp=time.time(),
                airtime_ms=airtime_ms,
            )

        return SendResult(
            success=False,
            protocol="meshtastic",
            error=f"lgw_send returned {result_code}",
            airtime_ms=airtime_ms,
        )

    async def _send_meshcore(
        self, text: str, destination: int | str, channel: int
    ) -> SendResult:
        """Send a message through the MeshCore companion."""
        if not self.meshcore_enabled:
            return SendResult(
                success=False,
                protocol="meshcore",
                error="MeshCore companion not connected",
            )

        is_broadcast = (
            destination == 0
            or destination == BROADCAST_ADDR_MC
            or str(destination).lower() in ("broadcast", "ffff", "0")
        )

        if is_broadcast:
            mc_result = await self._meshcore_tx.send_channel_message(
                channel, text
            )
        else:
            mc_result = await self._meshcore_tx.send_direct_message(
                destination, text
            )

        return SendResult(
            success=mc_result.success,
            protocol="meshcore",
            packet_id=mc_result.event_type,
            timestamp=time.time(),
            error=mc_result.error,
        )

    def _get_builder(self):
        """Lazy-load the Meshtastic packet builder."""
        if self._builder is not None:
            return self._builder
        try:
            from src.transmit.meshtastic_builder import (
                MeshtasticPacketBuilder,
            )
            self._builder = MeshtasticPacketBuilder(self._crypto)
            return self._builder
        except Exception:
            logger.exception("Failed to load MeshtasticPacketBuilder")
            return None

    def _build_hal_packet(self, packet_bytes: bytes):
        """Populate a LgwPktTxS struct from raw packet bytes."""
        from src.hal.sx1302_types import LgwPktTxS
        from src.hal.sx1302_wrapper import (
            BW_KHZ_TO_HAL,
            BW_250KHZ,
            MOD_LORA,
            TX_MODE_IMMEDIATE,
        )

        radio = self._radio_config
        tx_pkt = LgwPktTxS()
        tx_pkt.freq_hz = (
            int(radio.frequency_mhz * 1_000_000) if radio else 906_875_000
        )
        tx_pkt.tx_mode = TX_MODE_IMMEDIATE
        tx_pkt.count_us = 0
        tx_pkt.rf_chain = 0
        tx_pkt.rf_power = self._config.tx_power_dbm
        tx_pkt.modulation = MOD_LORA
        tx_pkt.freq_offset = 0
        bw_khz = int(radio.bandwidth_khz) if radio else 250
        tx_pkt.bandwidth = BW_KHZ_TO_HAL.get(bw_khz, BW_250KHZ)
        tx_pkt.datarate = radio.spreading_factor if radio else 11
        tx_pkt.coderate = self._resolve_coderate(
            radio.coding_rate if radio else "4/8"
        )
        tx_pkt.invert_pol = False
        tx_pkt.f_dev = 0
        tx_pkt.preamble = 16
        tx_pkt.no_crc = False
        tx_pkt.no_header = False
        tx_pkt.size = len(packet_bytes)

        for i, b in enumerate(packet_bytes[:256]):
            tx_pkt.payload[i] = b

        return tx_pkt

    async def _get_airtime(self, tx_pkt) -> int:
        """Compute airtime via the HAL (or estimate if unavailable)."""
        try:
            return await asyncio.to_thread(
                self._wrapper.get_time_on_air, tx_pkt
            )
        except Exception:
            return self._estimate_airtime(tx_pkt.size, tx_pkt.datarate)

    @staticmethod
    def _estimate_airtime(payload_size: int, sf: int) -> int:
        """Rough airtime estimate (ms) when HAL function unavailable."""
        symbol_time_ms = (2 ** sf) / 250.0
        n_symbols = 8 + max(
            ((8 * payload_size - 4 * sf + 28 + 16) // (4 * sf)) * 5 + 8, 0
        )
        return int((16 + n_symbols) * symbol_time_ms)

    def _next_packet_id(self) -> int:
        self._packet_counter = (self._packet_counter + 1) & 0xFFFFFFFF
        return self._packet_counter

    def _resolve_node_id(self) -> int:
        """Resolve the 4-byte Meshtastic source node ID.

        Priority:
          1. ``transmit.node_id`` from config (user override).
          2. Deterministic derivation from ``device.device_id`` so the
             ID stays the same across service restarts.
          3. CSPRNG fallback (rare: only legacy installs that never ran
             the wizard and have no device_id).
        """
        configured = self._config.node_id if self._config is not None else None
        if configured is not None and configured not in RESERVED_NODE_IDS:
            self._node_id_source = "config"
            logger.info(
                "source_node_id=0x%08x (source: config)", configured
            )
            return configured

        if self._device_id:
            value = self._derive_node_id(self._device_id)
            self._node_id_source = "derived"
            logger.info(
                "source_node_id=0x%08x (source: device_id, "
                "stable across restarts)",
                value,
            )
            return value

        value = self._random_non_reserved()
        self._node_id_source = "random"
        logger.warning(
            "source_node_id=0x%08x (source: RANDOM, will change on every "
            "restart). Set transmit.node_id in local.yaml or run "
            "`meshpoint setup` for a stable identity.",
            value,
        )
        return value

    def _persist_derived_node_id_if_needed(self) -> None:
        """Write the auto-derived node_id back to local.yaml so the dashboard
        and runtime stay in sync.

        Only fires when the source is ``derived`` (auto-computed from
        device_id). Pinned values are already on disk; ``random`` is a
        transient warning state we deliberately don't lock in.
        """
        if self._node_id_source != "derived":
            return
        try:
            from src.config import save_section_to_yaml
            save_section_to_yaml("transmit", {"node_id": self._source_node_id})
            logger.info(
                "Persisted auto-derived node_id=0x%08x to local.yaml",
                self._source_node_id,
            )
            if self._config is not None:
                self._config.node_id = self._source_node_id
            self._node_id_source = "config"
        except Exception as exc:
            logger.warning(
                "Could not persist auto-derived node_id (continuing with "
                "in-memory value): %s",
                exc,
            )

    @staticmethod
    def _derive_node_id(device_id: str) -> int:
        """Derive a 32-bit node_id from device_id, skipping reserved values."""
        digest = hashlib.sha256(device_id.encode("utf-8")).digest()
        for offset in range(0, 28, 4):
            value = int.from_bytes(digest[offset:offset + 4], "big")
            if value not in RESERVED_NODE_IDS:
                return value
        raise RuntimeError(
            "sha256 produced 7 reserved values in a row for device_id"
        )

    @staticmethod
    def _random_non_reserved() -> int:
        """Cryptographically random 32-bit node_id avoiding reserved values."""
        while True:
            value = secrets.randbits(32)
            if value not in RESERVED_NODE_IDS:
                return value

    def _resolve_channel(self, channel: int) -> tuple[int, bytes | None]:
        """Resolve channel index to (hash, encryption_key).

        Returns the correct hash and key for the given channel so TX
        packets are encrypted with the right PSK.
        """
        if self._crypto is None:
            return 0x08, None
        try:
            keys = self._crypto.get_all_keys()
            if channel == 0:
                key = keys[0]
                name = self._primary_channel_name
            else:
                channel_keys = list(self._crypto._keys.items())
                if channel - 1 < len(channel_keys):
                    ch_name, key = channel_keys[channel - 1]
                    name = ch_name
                else:
                    key = keys[0]
                    name = self._primary_channel_name

            h = self._crypto.compute_channel_hash(name, key)
            logger.info("Channel %d hash: 0x%02X (name=%s)", channel, h, name)
            return h, key
        except (IndexError, Exception):
            logger.debug("Channel hash fallback to 0x08", exc_info=True)
            return 0x08, None

    @staticmethod
    def _build_traceroute_reply_data(
        original, rx_snr: float | None
    ) -> tuple[list[int], list[int], list[int], list[int]]:
        """Build RouteDiscovery fields like Meshtastic firmware at the destination.

        Relays append node ids plus SNR on the way in. The target only appends the
        final-hop SNR (SNRonly) and does not add itself to ``route``. Meshtastic 2.5+
        also expects ``route_back`` / ``snr_back`` on the response.
        """
        payload = original.decoded_payload or {}
        route_nodes: list[int] = []
        for node_hex in payload.get("route") or []:
            try:
                route_nodes.append(int(node_hex, 16))
            except (TypeError, ValueError):
                continue

        snr_towards: list[int] = []
        for val in payload.get("snr_towards") or []:
            try:
                snr_towards.append(int(val))
            except (TypeError, ValueError):
                continue

        encoded_snr: int | None = None
        if rx_snr is not None:
            encoded_snr = int(round(float(rx_snr) * 4))

        if encoded_snr is not None:
            snr_towards.append(encoded_snr)

        requester = int(original.source_id, 16)
        route_back = [requester]
        snr_back = [encoded_snr] if encoded_snr is not None else []

        return route_nodes, snr_towards, route_back, snr_back

    def _resolve_channel_by_hash(self, channel_hash: int) -> tuple[int, bytes | None]:
        """Resolve encryption key from a captured on-air channel hash."""
        if self._crypto is None:
            return channel_hash, None
        try:
            primary_name = self._primary_channel_name
            all_keys = self._crypto.get_all_keys()
            if all_keys:
                primary_hash = self._crypto.compute_channel_hash(
                    primary_name, all_keys[0]
                )
                if primary_hash == channel_hash:
                    return channel_hash, all_keys[0]
            for i, (ch_name, key) in enumerate(self._crypto._keys.items(), start=1):
                if i < len(all_keys):
                    h = self._crypto.compute_channel_hash(ch_name, all_keys[i])
                    if h == channel_hash:
                        return channel_hash, all_keys[i]
            if all_keys:
                return channel_hash, all_keys[0]
        except Exception:
            logger.debug("Channel-by-hash lookup failed", exc_info=True)
        return channel_hash, None

    def _get_preset_name(self) -> str:
        """Derive the Meshtastic modem preset display name from radio params."""
        if not self._radio_config:
            return "LongFast"
        sf = self._radio_config.spreading_factor
        bw = int(self._radio_config.bandwidth_khz)
        return PRESET_DISPLAY_NAMES.get((sf, bw), "Custom")

    @staticmethod
    def _resolve_destination(
        destination: int | str, protocol: Protocol
    ) -> int:
        if isinstance(destination, str):
            dest_lower = destination.lower()
            if dest_lower in ("broadcast", "all", "ffff", "ffffffff", "0"):
                return BROADCAST_ADDR_MT
            raw = destination.lstrip("!")
            try:
                return int(raw, 16)
            except ValueError:
                return BROADCAST_ADDR_MT
        if destination == 0:
            return BROADCAST_ADDR_MT
        return destination

    @staticmethod
    def _resolve_coderate(coding_rate: str) -> int:
        """Map coding rate string to HAL constant."""
        rate_map = {
            "4/5": 0x01,
            "4/6": 0x02,
            "4/7": 0x03,
            "4/8": 0x04,
        }
        return rate_map.get(coding_rate, 0x01)
