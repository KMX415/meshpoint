"""Use the normal position scheduler with the selected PiMesh backend."""

from __future__ import annotations

import asyncio

from src.transmit.tx_service import SendResult


class PimeshPositionTransmitter:
    def __init__(self, tx_service, protocol):
        self.tx = tx_service
        self.protocol = protocol

    async def send_position(self, latitude, longitude, altitude=None):
        if self.protocol == "meshcore":
            mc = self.tx._meshcore_tx
            if mc is None or not mc.connected:
                return SendResult(
                    success=False, protocol="meshcore", error="MeshCore disconnected"
                )
            result = await mc.set_coordinates(latitude, longitude)
            if not result.success:
                return SendResult(
                    success=False, protocol="meshcore", error=result.error
                )
            # MeshCore carries location in its native identity advertisement.
            result = await mc.send_advert()
            return SendResult(
                success=result.success, protocol="meshcore", error=result.error
            )
        mt = self.tx._meshtasticd_tx
        if mt is None or not mt.connected:
            return SendResult(
                success=False, protocol="meshtastic", error="Meshtastic disconnected"
            )
        ok, result = await asyncio.to_thread(
            mt._source.request_send_position, latitude, longitude, altitude
        )
        return SendResult(
            success=ok,
            protocol="meshtastic",
            packet_id=result.get("packet_id", "")
            if ok and isinstance(result, dict)
            else "",
            error="" if ok else str(result),
        )
