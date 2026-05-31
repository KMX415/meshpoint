"""Meshtastic message transmission via meshtasticd TCP bridge."""

from __future__ import annotations

import asyncio
import logging
import time

from src.transmit.tx_service import SendResult

logger = logging.getLogger(__name__)


class MeshtasticdTxClient:
    """Sends messages through the live meshtasticd bridge capture source."""

    def __init__(self):
        self._source = None

    def set_source(self, source) -> None:
        """Bind to MeshtasticdBridgeSource for live interface access."""
        self._source = source
        logger.info("Meshtasticd TX client bound to capture source")

    @property
    def connected(self) -> bool:
        return self._source is not None and self._source.is_running

    def _interface(self):
        if self._source is None:
            return None
        return getattr(self._source, "interface", None)

    async def send_text(
        self,
        text: str,
        destination: int | str,
        channel: int = 0,
        want_ack: bool = False,
    ) -> SendResult:
        iface = self._interface()
        if iface is None:
            return SendResult(
                success=False,
                protocol="meshtastic",
                error="meshtasticd TX not connected",
            )

        dest_id = self._format_destination(destination)

        try:
            await asyncio.to_thread(
                iface.sendText,
                text,
                destinationId=dest_id,
                wantAck=want_ack,
                channelIndex=channel,
            )
            return SendResult(
                success=True,
                protocol="meshtastic",
                timestamp=time.time(),
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
        iface = self._interface()
        if iface is None or not hasattr(iface, "localNode"):
            return SendResult(
                success=False,
                protocol="meshtastic",
                error="meshtasticd TX not connected",
            )

        try:
            await asyncio.to_thread(
                iface.localNode.setOwner,
                long_name=long_name,
                short_name=short_name,
            )
            logger.info(
                "meshtasticd NodeInfo setOwner: long=%r short=%r hw=%d",
                long_name,
                short_name,
                hw_model,
            )
            return SendResult(
                success=True,
                protocol="meshtastic",
                timestamp=time.time(),
            )
        except Exception as exc:
            logger.exception("meshtasticd setOwner failed")
            return SendResult(
                success=False,
                protocol="meshtastic",
                error=str(exc),
            )

    @staticmethod
    def _format_destination(destination: int | str) -> int | str:
        if isinstance(destination, str):
            stripped = destination.strip()
            if stripped.startswith("!"):
                try:
                    return int(stripped[1:], 16)
                except ValueError:
                    return stripped
            if stripped.isdigit():
                return int(stripped)
            return stripped
        return destination
