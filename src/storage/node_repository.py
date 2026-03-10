from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from src.models.node import Node
from src.storage.database import DatabaseManager

logger = logging.getLogger(__name__)


class NodeRepository:
    """CRUD operations for mesh nodes."""

    def __init__(self, db: DatabaseManager):
        self._db = db

    async def upsert(self, node: Node) -> None:
        await self._db.execute(
            """
            INSERT INTO nodes (
                node_id, long_name, short_name, hardware_model,
                firmware_version, protocol, latitude, longitude,
                altitude, last_heard, first_seen, packet_count
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(node_id) DO UPDATE SET
                long_name = COALESCE(excluded.long_name, nodes.long_name),
                short_name = COALESCE(excluded.short_name, nodes.short_name),
                hardware_model = COALESCE(excluded.hardware_model, nodes.hardware_model),
                firmware_version = COALESCE(excluded.firmware_version, nodes.firmware_version),
                latitude = COALESCE(excluded.latitude, nodes.latitude),
                longitude = COALESCE(excluded.longitude, nodes.longitude),
                altitude = COALESCE(excluded.altitude, nodes.altitude),
                last_heard = excluded.last_heard,
                packet_count = nodes.packet_count + 1
            """,
            (
                node.node_id, node.long_name, node.short_name,
                node.hardware_model, node.firmware_version, node.protocol,
                node.latitude, node.longitude, node.altitude,
                node.last_heard.isoformat(), node.first_seen.isoformat(),
                node.packet_count,
            ),
        )
        await self._db.commit()

    async def get_by_id(self, node_id: str) -> Optional[Node]:
        row = await self._db.fetch_one(
            "SELECT * FROM nodes WHERE node_id = ?", (node_id,)
        )
        if not row:
            return None
        return self._row_to_node(row)

    async def get_all(self, limit: int = 500) -> list[Node]:
        rows = await self._db.fetch_all(
            "SELECT * FROM nodes ORDER BY last_heard DESC LIMIT ?", (limit,)
        )
        return [self._row_to_node(r) for r in rows]

    async def get_count(self) -> int:
        row = await self._db.fetch_one("SELECT COUNT(*) as cnt FROM nodes")
        return row["cnt"] if row else 0

    async def get_with_position(self) -> list[Node]:
        rows = await self._db.fetch_all(
            "SELECT * FROM nodes WHERE latitude IS NOT NULL AND longitude IS NOT NULL"
        )
        return [self._row_to_node(r) for r in rows]

    async def increment_packet_count(self, node_id: str) -> None:
        await self._db.execute(
            "UPDATE nodes SET packet_count = packet_count + 1, last_heard = ? WHERE node_id = ?",
            (datetime.now(timezone.utc).isoformat(), node_id),
        )
        await self._db.commit()

    @staticmethod
    def _row_to_node(row: dict) -> Node:
        return Node(
            node_id=row["node_id"],
            long_name=row.get("long_name"),
            short_name=row.get("short_name"),
            hardware_model=row.get("hardware_model"),
            firmware_version=row.get("firmware_version"),
            protocol=row.get("protocol", "meshtastic"),
            latitude=row.get("latitude"),
            longitude=row.get("longitude"),
            altitude=row.get("altitude"),
            last_heard=datetime.fromisoformat(row["last_heard"]),
            first_seen=datetime.fromisoformat(row["first_seen"]),
            packet_count=row.get("packet_count", 0),
        )
