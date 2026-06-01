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
            await self._tx.send_traceroute_reply(packet)
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
