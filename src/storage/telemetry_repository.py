from __future__ import annotations

import logging
from datetime import datetime

from src.models.telemetry import Telemetry
from src.storage.database import DatabaseManager

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
        self, node_id: str, limit: int = 100
    ) -> list[Telemetry]:
        rows = await self._db.fetch_all(
            "SELECT * FROM telemetry WHERE node_id = ? ORDER BY timestamp DESC LIMIT ?",
            (node_id, limit),
        )
        return [self._row_to_telemetry(r) for r in rows]

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
