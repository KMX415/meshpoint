from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from src.models.telemetry import Telemetry
from src.storage.database import DatabaseManager
from src.storage.time_bucket import bucket_seconds

logger = logging.getLogger(__name__)


class TelemetryRepository:
    """CRUD operations for device telemetry records."""

    def __init__(self, db: DatabaseManager):
        self._db = db

    async def insert(self, telemetry: Telemetry) -> None:
        await self._db.execute(
            """
            INSERT INTO telemetry (
                node_id, battery_level, voltage, temperature,
                humidity, barometric_pressure, channel_utilization,
                air_util_tx, uptime_seconds, timestamp
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                telemetry.node_id, telemetry.battery_level,
                telemetry.voltage, telemetry.temperature,
                telemetry.humidity, telemetry.barometric_pressure,
                telemetry.channel_utilization, telemetry.air_util_tx,
                telemetry.uptime_seconds, telemetry.timestamp.isoformat(),
            ),
        )
        await self._db.commit()

    async def get_latest_for_node(self, node_id: str) -> Telemetry | None:
        row = await self._db.fetch_one(
            "SELECT * FROM telemetry WHERE node_id = ? ORDER BY timestamp DESC LIMIT 1",
            (node_id,),
        )
        if not row:
            return None
        return self._row_to_telemetry(row)

    async def get_history(
        self,
        node_id: str,
        limit: int = 300,
        hours: float | None = None,
    ) -> list[Telemetry]:
        """Return telemetry oldest-first for charting (ASC).

        When ``hours`` is set, rows are averaged into at most ``limit``
        time buckets across the real data span so newest samples are not
        silently dropped by a plain LIMIT.
        """
        if hours is not None and hours > 0:
            since = (
                datetime.now(timezone.utc) - timedelta(hours=hours)
            ).isoformat()
            span_row = await self._db.fetch_one(
                "SELECT MIN(timestamp) AS lo, MAX(timestamp) AS hi "
                "FROM telemetry WHERE node_id = ? AND timestamp >= ?",
                (node_id, since),
            )
            bucket_secs = bucket_seconds(span_row, limit, hours)
            rows = await self._db.fetch_all(
                """
                SELECT * FROM (
                    SELECT
                        node_id,
                        AVG(battery_level) AS battery_level,
                        AVG(voltage) AS voltage,
                        AVG(temperature) AS temperature,
                        AVG(humidity) AS humidity,
                        AVG(barometric_pressure) AS barometric_pressure,
                        AVG(channel_utilization) AS channel_utilization,
                        AVG(air_util_tx) AS air_util_tx,
                        AVG(uptime_seconds) AS uptime_seconds,
                        MIN(timestamp) AS timestamp
                    FROM telemetry
                    WHERE node_id = ? AND timestamp >= ?
                    GROUP BY CAST(strftime('%s', timestamp) AS INTEGER) / ?
                    ORDER BY timestamp DESC
                    LIMIT ?
                )
                ORDER BY timestamp ASC
                """,
                (node_id, since, bucket_secs, limit),
            )
        else:
            rows = await self._db.fetch_all(
                """
                SELECT * FROM telemetry
                WHERE node_id = ? ORDER BY timestamp ASC LIMIT ?
                """,
                (node_id, limit),
            )
        return [self._row_to_telemetry(r) for r in rows]

    async def get_count(self) -> int:
        row = await self._db.fetch_one("SELECT COUNT(*) AS cnt FROM telemetry")
        return int(row["cnt"]) if row else 0

    async def cleanup_old(self, max_retained: int) -> int:
        """Prune oldest telemetry rows once the table exceeds max_retained."""
        total = await self.get_count()
        if total <= max_retained:
            return 0
        excess = total - max_retained
        await self._db.execute(
            "DELETE FROM telemetry WHERE id IN "
            "(SELECT id FROM telemetry ORDER BY timestamp ASC LIMIT ?)",
            (excess,),
        )
        await self._db.commit()
        logger.info("Cleaned up %d old telemetry rows", excess)
        return excess

    @staticmethod
    def _row_to_telemetry(row: dict) -> Telemetry:
        return Telemetry(
            node_id=row["node_id"],
            battery_level=row.get("battery_level"),
            voltage=row.get("voltage"),
            temperature=row.get("temperature"),
            humidity=row.get("humidity"),
            barometric_pressure=row.get("barometric_pressure"),
            channel_utilization=row.get("channel_utilization"),
            air_util_tx=row.get("air_util_tx"),
            uptime_seconds=row.get("uptime_seconds"),
            timestamp=datetime.fromisoformat(row["timestamp"]),
        )
