from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from datetime import timedelta

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
                firmware_version, protocol, role, latitude, longitude,
                altitude, last_heard, first_seen, packet_count
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(node_id) DO UPDATE SET
                long_name = CASE
                    WHEN excluded.long_name IS NULL OR excluded.long_name = ''
                        THEN nodes.long_name
                    WHEN nodes.long_name IS NULL OR nodes.long_name = ''
                        THEN excluded.long_name
                    WHEN nodes.protocol = 'meshcore'
                         AND LOWER(nodes.long_name) = LOWER(nodes.node_id)
                        THEN excluded.long_name
                    ELSE nodes.long_name
                END,
                short_name = COALESCE(excluded.short_name, nodes.short_name),
                hardware_model = COALESCE(excluded.hardware_model, nodes.hardware_model),
                firmware_version = COALESCE(excluded.firmware_version, nodes.firmware_version),
                role = COALESCE(excluded.role, nodes.role),
                latitude = COALESCE(excluded.latitude, nodes.latitude),
                longitude = COALESCE(excluded.longitude, nodes.longitude),
                altitude = COALESCE(excluded.altitude, nodes.altitude),
                last_heard = excluded.last_heard,
                packet_count = nodes.packet_count + 1
            """,
            (
                node.node_id, node.long_name, node.short_name,
                node.hardware_model, node.firmware_version, node.protocol,
                node.role, node.latitude, node.longitude, node.altitude,
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

    async def get_active_count(self, hours: int = 24) -> int:
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
        row = await self._db.fetch_one(
            "SELECT COUNT(*) as cnt FROM nodes WHERE last_heard >= ?", (cutoff,)
        )
        return row["cnt"] if row else 0

    async def get_with_position(self) -> list[Node]:
        rows = await self._db.fetch_all(
            "SELECT * FROM nodes WHERE latitude IS NOT NULL AND longitude IS NOT NULL"
        )
        return [self._row_to_node(r) for r in rows]

    async def get_all_with_signal(self, limit: int = 500) -> list[dict]:
        """Return nodes with latest signal and telemetry from joined tables."""
        rows = await self._db.fetch_all(
            """
            SELECT n.*,
                   p.rssi AS latest_rssi,
                   p.snr AS latest_snr,
                   p.hop_limit AS latest_hop_limit,
                   p.hop_start AS latest_hop_start,
                   t.battery_level AS latest_battery,
                   t.voltage AS latest_voltage,
                   t.temperature AS latest_temperature,
                   t.humidity AS latest_humidity,
                   t.channel_utilization AS latest_channel_util,
                   t.air_util_tx AS latest_air_util
            FROM nodes n
            LEFT JOIN (
                SELECT source_id,
                       rssi, snr, hop_limit, hop_start,
                       ROW_NUMBER() OVER (PARTITION BY source_id ORDER BY timestamp DESC) AS rn
                FROM packets
            ) p ON p.source_id = n.node_id AND p.rn = 1
            LEFT JOIN (
                SELECT node_id,
                       battery_level, voltage, temperature, humidity,
                       channel_utilization, air_util_tx,
                       ROW_NUMBER() OVER (PARTITION BY node_id ORDER BY timestamp DESC) AS rn
                FROM telemetry
            ) t ON t.node_id = n.node_id AND t.rn = 1
            ORDER BY n.last_heard DESC
            LIMIT ?
            """,
            (limit,),
        )
        return [self._enrich_row(row) for row in rows]

    @staticmethod
    def _enrich_row(row: dict) -> dict:
        """Build an enriched node dict from a joined query row."""
        node = NodeRepository._row_to_node(row)
        d = node.to_dict()
        d["latest_rssi"] = row.get("latest_rssi")
        d["latest_snr"] = row.get("latest_snr")
        d["latest_battery"] = row.get("latest_battery")
        d["latest_voltage"] = row.get("latest_voltage")
        d["latest_temperature"] = row.get("latest_temperature")
        d["latest_humidity"] = row.get("latest_humidity")
        d["latest_channel_util"] = row.get("latest_channel_util")
        d["latest_air_util"] = row.get("latest_air_util")
        hop_start = row.get("latest_hop_start", 0) or 0
        hop_limit = row.get("latest_hop_limit", 0) or 0
        d["latest_hops"] = max(0, hop_start - hop_limit)
        return d

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
            role=row.get("role"),
            latitude=row.get("latitude"),
            longitude=row.get("longitude"),
            altitude=row.get("altitude"),
            last_heard=datetime.fromisoformat(row["last_heard"]),
            first_seen=datetime.fromisoformat(row["first_seen"]),
            packet_count=row.get("packet_count", 0),
        )
