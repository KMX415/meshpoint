from __future__ import annotations

import json
import logging
from datetime import datetime

from src.models.packet import Packet, PacketType, Protocol
from src.models.signal import SignalMetrics
from src.storage.database import DatabaseManager

logger = logging.getLogger(__name__)


class PacketRepository:
    """CRUD operations for captured mesh packets."""

    def __init__(self, db: DatabaseManager):
        self._db = db

    async def insert(self, packet: Packet) -> None:
        payload_json = (
            json.dumps(packet.decoded_payload)
            if packet.decoded_payload
            else None
        )
        await self._db.execute(
            """
            INSERT INTO packets (
                packet_id, source_id, destination_id, protocol,
                packet_type, hop_limit, hop_start, channel_hash,
                want_ack, via_mqtt, decoded_payload, decrypted,
                rssi, snr, frequency_mhz, spreading_factor,
                bandwidth_khz, capture_source, timestamp
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                packet.packet_id, packet.source_id,
                packet.destination_id, packet.protocol.value,
                packet.packet_type.value, packet.hop_limit,
                packet.hop_start, packet.channel_hash,
                int(packet.want_ack), int(packet.via_mqtt),
                payload_json, int(packet.decrypted),
                packet.signal.rssi if packet.signal else None,
                packet.signal.snr if packet.signal else None,
                packet.signal.frequency_mhz if packet.signal else None,
                packet.signal.spreading_factor if packet.signal else None,
                packet.signal.bandwidth_khz if packet.signal else None,
                packet.capture_source, packet.timestamp.isoformat(),
            ),
        )
        await self._db.commit()

    async def get_recent(self, limit: int = 100) -> list[Packet]:
        rows = await self._db.fetch_all(
            "SELECT * FROM packets ORDER BY timestamp DESC LIMIT ?",
            (limit,),
        )
        return [self._row_to_packet(r) for r in rows]

    async def get_by_source(
        self, source_id: str, limit: int = 100
    ) -> list[Packet]:
        rows = await self._db.fetch_all(
            "SELECT * FROM packets WHERE source_id = ? ORDER BY timestamp DESC LIMIT ?",
            (source_id, limit),
        )
        return [self._row_to_packet(r) for r in rows]

    async def get_count(self) -> int:
        row = await self._db.fetch_one("SELECT COUNT(*) as cnt FROM packets")
        return row["cnt"] if row else 0

    async def get_count_since(self, since: datetime) -> int:
        row = await self._db.fetch_one(
            "SELECT COUNT(*) as cnt FROM packets WHERE timestamp >= ?",
            (since.isoformat(),),
        )
        return row["cnt"] if row else 0

    async def get_protocol_distribution(self) -> dict[str, int]:
        rows = await self._db.fetch_all(
            "SELECT protocol, COUNT(*) as cnt FROM packets GROUP BY protocol"
        )
        return {r["protocol"]: r["cnt"] for r in rows}

    async def get_type_distribution(self) -> dict[str, int]:
        rows = await self._db.fetch_all(
            "SELECT packet_type, COUNT(*) as cnt FROM packets GROUP BY packet_type"
        )
        return {r["packet_type"]: r["cnt"] for r in rows}

    async def cleanup_old(self, max_retained: int) -> int:
        total = await self.get_count()
        if total <= max_retained:
            return 0
        excess = total - max_retained
        await self._db.execute(
            "DELETE FROM packets WHERE id IN (SELECT id FROM packets ORDER BY timestamp ASC LIMIT ?)",
            (excess,),
        )
        await self._db.commit()
        logger.info("Cleaned up %d old packets", excess)
        return excess

    @staticmethod
    def _row_to_packet(row: dict) -> Packet:
        signal = None
        if row.get("rssi") is not None:
            signal = SignalMetrics(
                rssi=row["rssi"],
                snr=row.get("snr", 0.0),
                frequency_mhz=row.get("frequency_mhz", 906.875),
                spreading_factor=row.get("spreading_factor", 11),
                bandwidth_khz=row.get("bandwidth_khz", 250.0),
            )

        decoded = None
        if row.get("decoded_payload"):
            decoded = json.loads(row["decoded_payload"])

        return Packet(
            packet_id=row["packet_id"],
            source_id=row["source_id"],
            destination_id=row["destination_id"],
            protocol=Protocol(row["protocol"]),
            packet_type=PacketType(row["packet_type"]),
            hop_limit=row.get("hop_limit", 0),
            hop_start=row.get("hop_start", 0),
            channel_hash=row.get("channel_hash", 0),
            want_ack=bool(row.get("want_ack", 0)),
            via_mqtt=bool(row.get("via_mqtt", 0)),
            decoded_payload=decoded,
            decrypted=bool(row.get("decrypted", 0)),
            signal=signal,
            capture_source=row.get("capture_source", "unknown"),
            timestamp=datetime.fromisoformat(row["timestamp"]),
        )
