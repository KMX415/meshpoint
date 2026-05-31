"""Meshtastic message transmission via meshtasticd TCP bridge."""

from __future__ import annotations

import asyncio
import logging
import time

from src.models.packet import Protocol
from src.transmit.tx_service import SendResult, TxService

logger = logging.getLogger(__name__)


class MeshtasticdTxClient:
    """Sends messages through the live meshtasticd bridge capture source."""

    def __init__(self):
        self._source = None

    def set_source(self, source) -> None:
        """Bind to MeshtasticdBridgeSource for bridge command access."""
        self._source = source
        logger.info("Meshtasticd TX client bound to capture source")

    @property
    def connected(self) -> bool:
        return self._source is not None and self._source.is_running

    async def send_text(
        self,
        text: str,
        destination: int | str,
        channel: int = 0,
        want_ack: bool = False,
    ) -> SendResult:
        source = self._source
        if source is None or not source.is_running:
            return SendResult(
                success=False,
                protocol="meshtastic",
                error="meshtasticd TX not connected",
            )

        dest_id = self._format_destination(destination)

        try:
            success, error = await asyncio.to_thread(
                source.request_send_text,
                text,
                dest_id,
                channel,
                want_ack,
            )
            if success:
                return SendResult(
                    success=True,
                    protocol="meshtastic",
                    timestamp=time.time(),
                )
            return SendResult(
                success=False,
                protocol="meshtastic",
                error=error or "meshtasticd sendText failed",
            )
        except Exception as exc:
            logger.exception("meshtasticd sendText failed")
            return SendResult(
                success=False,
                protocol="meshtastic",
                error=str(exc),
            )

    async def send_nodeinfo(
        self,
        long_name: str,
        short_name: str,
        hw_model: int = 37,
    ) -> SendResult:
        source = self._source
        if source is None or not source.is_running:
            return SendResult(
                success=False,
                protocol="meshtastic",
                error="meshtasticd TX not connected",
            )

        try:
            success, error = await asyncio.to_thread(
                source.request_send_nodeinfo,
                long_name,
                short_name,
                hw_model,
            )
            if success:
                return SendResult(
                    success=True,
                    protocol="meshtastic",
                    timestamp=time.time(),
                )
            return SendResult(
                success=False,
                protocol="meshtastic",
                error=error or "meshtasticd setOwner failed",
            )
        except Exception as exc:
            logger.exception("meshtasticd setOwner failed")
            return SendResult(
                success=False,
                protocol="meshtastic",
                error=str(exc),
            )

    @staticmethod
    def _format_destination(destination: int | str) -> int:
        """Map Meshpoint message destinations to meshtastic node nums."""
        return TxService._resolve_destination(destination, Protocol.MESHTASTIC)
