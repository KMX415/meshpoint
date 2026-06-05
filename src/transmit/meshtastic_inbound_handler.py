"""Automatic Meshtastic responses to inbound packets addressed to us."""

from __future__ import annotations

import logging

from src.models.packet import Packet, PacketType, Protocol
from src.transmit.tx_service import TxService

logger = logging.getLogger(__name__)


class MeshtasticInboundHandler:
    """Fire routing ACKs and traceroute replies for inbound DMs."""

    def __init__(self, tx_service: TxService, our_node_id: int):
        self._tx = tx_service
        self._our_node_hex = f"{our_node_id:08x}"

    async def handle(self, packet: Packet) -> None:
        if packet.protocol != Protocol.MESHTASTIC or not packet.decrypted:
            return
        if packet.source_id.lower() == self._our_node_hex:
            return

        dest = (packet.destination_id or "").lower()
        if dest != self._our_node_hex:
            return

        if packet.packet_type == PacketType.TRACEROUTE:
            logger.info(
                "Inbound traceroute from %s (id=%s ch=0x%02x)",
                packet.source_id,
                packet.packet_id,
                packet.channel_hash or 0,
            )
            result = await self._tx.send_traceroute_reply(packet)
            if result.success:
                payload = packet.decoded_payload or {}
                logger.info(
                    "Traceroute reply TX OK to %s (reply id=%s, inbound route=%d snr=%d)",
                    packet.source_id,
                    result.packet_id,
                    len(payload.get("route") or []),
                    len(payload.get("snr_towards") or []),
                )
            else:
                logger.warning(
                    "Traceroute reply failed to %s: %s",
                    packet.source_id,
                    result.error,
                )
            return

        if packet.packet_type == PacketType.TELEMETRY:
            variant = (packet.decoded_payload or {}).get(
                "telemetry_variant", "device_metrics"
            )
            logger.info(
                "Inbound telemetry request from %s (id=%s variant=%s ch=0x%02x "
                "hop=%d/%d)",
                packet.source_id,
                packet.packet_id,
                variant,
                packet.channel_hash or 0,
                packet.hop_limit,
                packet.hop_start,
            )
            result = await self._tx.send_telemetry_reply(packet)
            if result.success:
                logger.info(
                    "Telemetry reply TX OK to %s (reply id=%s, variant=%s, pki=%s, "
                    "request_id=%s)",
                    packet.source_id,
                    result.packet_id,
                    variant,
                    packet.channel_hash == 0,
                    packet.packet_id,
                )
            else:
                logger.warning(
                    "Telemetry reply failed to %s: %s",
                    packet.source_id,
                    result.error,
                )
            return

        if packet.packet_type == PacketType.TEXT and packet.want_ack:
            await self._tx.send_routing_ack(packet)


def should_handle_inbound(packet: Packet, our_node_hex: str) -> bool:
    """True when the packet is a decrypted Meshtastic frame to our node."""
    if packet.protocol != Protocol.MESHTASTIC or not packet.decrypted:
        return False
    if packet.source_id.lower() == our_node_hex:
        return False
    return (packet.destination_id or "").lower() == our_node_hex
