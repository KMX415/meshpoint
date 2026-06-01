"""Tests for inbound Meshtastic auto-responses."""

from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, MagicMock

from src.models.packet import Packet, PacketType, Protocol
from src.transmit.meshtastic_inbound_handler import MeshtasticInboundHandler


class TestMeshtasticInboundHandler(unittest.IsolatedAsyncioTestCase):
    async def test_routing_ack_for_want_ack_text(self):
        tx = MagicMock()
        tx.send_routing_ack = AsyncMock(return_value=MagicMock(success=True))
        handler = MeshtasticInboundHandler(tx, our_node_id=0x12345678)

        packet = Packet(
            packet_id="0000000a",
            source_id="aabbccdd",
            destination_id="12345678",
            protocol=Protocol.MESHTASTIC,
            packet_type=PacketType.TEXT,
            want_ack=True,
            decrypted=True,
            decoded_payload={"text": "hi"},
        )
        await handler.handle(packet)
        tx.send_routing_ack.assert_awaited_once_with(packet)

    async def test_ignores_broadcast(self):
        tx = MagicMock()
        tx.send_routing_ack = AsyncMock()
        handler = MeshtasticInboundHandler(tx, our_node_id=0x12345678)

        packet = Packet(
            packet_id="1",
            source_id="aabbccdd",
            destination_id="ffffffff",
            protocol=Protocol.MESHTASTIC,
            packet_type=PacketType.TEXT,
            want_ack=True,
            decrypted=True,
        )
        await handler.handle(packet)
        tx.send_routing_ack.assert_not_called()


if __name__ == "__main__":
    unittest.main()
