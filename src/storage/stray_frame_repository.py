"""Persistence for undecodable RF frames (stray / unknown protocol)."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from src.models.packet import RawCapture
from src.storage.database import DatabaseManager

logger = logging.getLogger(__name__)

MESHTASTIC_HEADER_SIZE = 16


@dataclass
class StrayFrame:
    id: int
    frame_size: int
    channel_hash: int | None
    frequency_mhz: float | None
    spreading_factor: int | None
    bandwidth_khz: float | None
    rssi: float | None
    snr: float | None
    capture_source: str | None
    timestamp: datetime

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "frame_size": self.frame_size,
            "channel_hash": self.channel_hash,
            "frequency_mhz": self.frequency_mhz,
            "spreading_factor": self.spreading_factor,
            "bandwidth_khz": self.bandwidth_khz,
            "rssi": self.rssi,
            "snr": self.snr,
            "capture_source": self.capture_source,
            "timestamp": self.timestamp.isoformat(),
        }


class StrayFrameRepository:
    """CRUD for frames that fail both Meshtastic and MeshCore decode."""

    def __init__(self, db: DatabaseManager):
        self._db = db

    async def insert_from_capture(self, raw: RawCapture) -> None:
        signal = raw.signal
        channel_hash = _peek_channel_hash(raw.payload)
        ts = raw.timestamp or datetime.now(timezone.utc)
        await self._db.execute(
            """
            INSERT INTO stray_frames (
                frame_size, channel_hash, frequency_mhz, spreading_factor,
                bandwidth_khz, rssi, snr, capture_source, timestamp
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                len(raw.payload),
                channel_hash,
                signal.frequency_mhz if signal else None,
                signal.spreading_factor if signal else None,
                signal.bandwidth_khz if signal else None,
                signal.rssi if signal else None,
                signal.snr if signal else None,
                raw.capture_source,
                ts.isoformat(),
            ),
        )
        await self._db.commit()

    async def list_recent(
        self,
        *,
        limit: int = 200,
        hours: float | None = 24,
        min_rssi: float | None = None,
    ) -> list[StrayFrame]:
        clauses = []
        params: list = []
        if hours is not None and hours > 0:
            cutoff = (
                datetime.now(timezone.utc) - timedelta(hours=hours)
            ).isoformat()
            clauses.append("timestamp >= ?")
            params.append(cutoff)
        if min_rssi is not None:
            clauses.append("rssi >= ?")
            params.append(min_rssi)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(limit)
        rows = await self._db.fetch_all(
            f"""
            SELECT * FROM stray_frames
            {where}
            ORDER BY timestamp DESC
            LIMIT ?
            """,
            tuple(params),
        )
        return [self._row_to_frame(row) for row in rows]

    async def get_count(self) -> int:
        row = await self._db.fetch_one("SELECT COUNT(*) AS cnt FROM stray_frames")
        return int(row["cnt"]) if row else 0

    async def cleanup(self, max_retained: int, retention_hours: float) -> int:
        """Drop rows older than retention window, then trim to max_retained."""
        removed = 0
        if retention_hours > 0:
            cutoff = (
                datetime.now(timezone.utc) - timedelta(hours=retention_hours)
            ).isoformat()
            result = await self._db.execute(
                "DELETE FROM stray_frames WHERE timestamp < ?",
                (cutoff,),
            )
            removed += int(getattr(result, "rowcount", 0) or 0)

        total = await self.get_count()
        if total > max_retained:
            excess = total - max_retained
            await self._db.execute(
                """
                DELETE FROM stray_frames WHERE id IN (
                    SELECT id FROM stray_frames
                    ORDER BY timestamp ASC
                    LIMIT ?
                )
                """,
                (excess,),
            )
            removed += excess

        if removed:
            await self._db.commit()
            logger.info("Pruned %d stray frame rows", removed)
        return removed

    @staticmethod
    def _row_to_frame(row: dict) -> StrayFrame:
        return StrayFrame(
            id=row["id"],
            frame_size=row["frame_size"],
            channel_hash=row.get("channel_hash"),
            frequency_mhz=row.get("frequency_mhz"),
            spreading_factor=row.get("spreading_factor"),
            bandwidth_khz=row.get("bandwidth_khz"),
            rssi=row.get("rssi"),
            snr=row.get("snr"),
            capture_source=row.get("capture_source"),
            timestamp=datetime.fromisoformat(row["timestamp"]),
        )


def _peek_channel_hash(payload: bytes) -> int | None:
    """Best-effort channel hash byte when a Meshtastic-shaped header exists."""
    if len(payload) < MESHTASTIC_HEADER_SIZE:
        return None
    try:
        return int(payload[13])
    except (IndexError, TypeError, ValueError):
        return None
