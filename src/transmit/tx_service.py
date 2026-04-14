"""Unified message transmission service for Meshtastic and MeshCore.

Routes outbound messages to the appropriate TX path: native SX1261
for Meshtastic, USB/TCP companion for MeshCore.
"""

from __future__ import annotations

import asyncio
import logging
import random
import time
from dataclasses import dataclass
from typing import Optional

from src.models.packet import Protocol
from src.transmit.duty_cycle import DutyCycleTracker

logger = logging.getLogger(__name__)

BROADCAST_ADDR_MT = 0xFFFFFFFF
BROADCAST_ADDR_MC = 0xFFFF

PRESET_DISPLAY_NAMES: dict[tuple[int, int], str] = {
    (7, 250): "ShortFast",
    (7, 500): "ShortTurbo",
    (8, 250): "ShortSlow",
    (9, 250): "MediumFast",
    (10, 250): "MediumSlow",
    (11, 250): "LongFast",
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
    ):
        self._wrapper = wrapper
        self._crypto = crypto
        self._channel_plan = channel_plan
        self._config = transmit_config
        self._meshcore_tx = meshcore_tx
        self._duty = duty_tracker
        self._radio_config = radio_config
        self._primary_channel_name = primary_channel_name
        self._builder = None
        self._packet_counter = random.randint(1, 0xFFFF)
        self._source_node_id = self._resolve_node_id()

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

        packet_bytes = builder.build_text_message(
            text=text,
            dest=dest_int,
            source_id=self._source_node_id,
            packet_id=packet_id,
            channel_key=channel_key,
            channel_hash=channel_hash,
            hop_limit=3,
            hop_start=3,
            want_ack=want_ack,
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
        """Get or generate a 4-byte Meshtastic node ID."""
        if (
            self._config is not None
            and self._config.node_id is not None
            and self._config.node_id != 0
        ):
            return self._config.node_id
        return random.randint(0x01000000, 0xFFFFFFFE)

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
