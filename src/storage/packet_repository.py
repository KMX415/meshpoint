from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone

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
                want_ack, via_mqtt, relay_node, decoded_payload, decrypted,
                rssi, snr, frequency_mhz, spreading_factor,
                bandwidth_khz, capture_source, timestamp
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                packet.packet_id, packet.source_id,
                packet.destination_id, packet.protocol.value,
                packet.packet_type.value, packet.hop_limit,
                packet.hop_start, packet.channel_hash,
                int(packet.want_ack), int(packet.via_mqtt),
                packet.relay_node, payload_json, int(packet.decrypted),
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

    async def get_signal_history(
        self,
        source_id: str,
        limit: int = 500,
        hours: float | None = 24,
    ) -> list[dict]:
        """RSSI/SNR samples from any packet by this node, oldest-first."""
        if hours is not None and hours > 0:
            since = (
                datetime.now(timezone.utc) - timedelta(hours=hours)
            ).isoformat()
            rows = await self._db.fetch_all(
                """
                SELECT timestamp, rssi, snr FROM packets
                WHERE source_id = ? AND rssi IS NOT NULL AND timestamp >= ?
                ORDER BY timestamp ASC
                LIMIT ?
                """,
                (source_id, since, limit),
            )
        else:
            rows = await self._db.fetch_all(
                """
                SELECT timestamp, rssi, snr FROM packets
                WHERE source_id = ? AND rssi IS NOT NULL
                ORDER BY timestamp ASC
                LIMIT ?
                """,
                (source_id, limit),
            )
        return [
            {
                "timestamp": row["timestamp"],
                "rssi": row["rssi"],
                "snr": row.get("snr"),
            }
            for row in rows
        ]

    async def get_source_id_by_packet_id(self, packet_id: str) -> str:
        if not packet_id:
            return ""
        row = await self._db.fetch_one(
            "SELECT source_id FROM packets WHERE packet_id = ? LIMIT 1",
            (packet_id,),
        )
        return row["source_id"] if row else ""

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

    async def get_topology_graph(
        self,
        hours: float = 24,
        *,
        edge_limit: int = 500,
        route_limit: int = 100,
    ) -> dict:
        """Build nodes, NEIGHBORINFO edges, and TRACEROUTE paths for the graph tab."""
        hours = max(1.0, min(float(hours), 168.0))
        since = (
            datetime.now(timezone.utc) - timedelta(hours=hours)
        ).isoformat()

        ni_rows = await self._db.fetch_all(
            """
            SELECT source_id, decoded_payload, rssi, snr, timestamp, protocol
            FROM packets
            WHERE packet_type = 'neighborinfo'
              AND decoded_payload IS NOT NULL
              AND timestamp >= ?
            ORDER BY timestamp DESC
            LIMIT ?
            """,
            (since, edge_limit),
        )

        edges_by_key: dict[str, dict] = {}
        for row in ni_rows:
            source = row["source_id"]
            try:
                payload = json.loads(row["decoded_payload"])
            except (json.JSONDecodeError, TypeError):
                continue

            neighbors = payload.get("neighbors", [])
            if not isinstance(neighbors, list):
                continue

            for neighbor in neighbors:
                nid = neighbor.get("node_id") or neighbor.get("id")
                if not nid:
                    continue
                target = str(nid).lower().lstrip("!")
                link_key = f"{min(source, target)}_{max(source, target)}"
                if link_key in edges_by_key:
                    continue

                neighbor_snr = neighbor.get("snr")
                rssi = row.get("rssi")
                weak = rssi is not None and rssi < -110

                edges_by_key[link_key] = {
                    "source": source,
                    "target": target,
                    "rssi": round(rssi, 1) if rssi is not None else None,
                    "snr": (
                        round(row["snr"], 1)
                        if row.get("snr") is not None
                        else None
                    ),
                    "neighbor_snr": (
                        round(neighbor_snr, 1)
                        if neighbor_snr is not None
                        else None
                    ),
                    "last_seen": row["timestamp"],
                    "weak": weak,
                }

        route_rows = await self._db.fetch_all(
            """
            SELECT source_id, decoded_payload, timestamp
            FROM packets
            WHERE packet_type = 'traceroute'
              AND decoded_payload IS NOT NULL
              AND timestamp >= ?
            ORDER BY timestamp DESC
            LIMIT ?
            """,
            (since, route_limit),
        )

        routes: list[dict] = []
        seen_routes: set[str] = set()
        for row in route_rows:
            try:
                payload = json.loads(row["decoded_payload"])
            except (json.JSONDecodeError, TypeError):
                continue
            route = payload.get("route")
            if not isinstance(route, list) or len(route) < 2:
                continue
            normalized = [str(n).lower().lstrip("!") for n in route]
            key = f"{row['source_id']}:{'-'.join(normalized)}"
            if key in seen_routes:
                continue
            seen_routes.add(key)
            routes.append({
                "source": row["source_id"],
                "route": normalized,
                "last_seen": row["timestamp"],
            })

        node_ids: set[str] = set()
        for edge in edges_by_key.values():
            node_ids.add(edge["source"])
            node_ids.add(edge["target"])
        for route in routes:
            node_ids.update(route["route"])

        nodes: list[dict] = []
        if node_ids:
            counts = await self._db.fetch_all(
                f"""
                SELECT source_id, protocol, COUNT(*) AS packet_count,
                       MAX(rssi) AS latest_rssi
                FROM packets
                WHERE timestamp >= ? AND source_id IN ({",".join("?" * len(node_ids))})
                GROUP BY source_id, protocol
                """,
                (since, *sorted(node_ids)),
            )
            count_by_id: dict[str, dict] = {}
            for row in counts:
                nid = row["source_id"]
                entry = count_by_id.setdefault(nid, {
                    "packet_count": 0,
                    "latest_rssi": row.get("latest_rssi"),
                    "protocol": row.get("protocol") or "meshtastic",
                })
                entry["packet_count"] += int(row["packet_count"] or 0)
                rssi = row.get("latest_rssi")
                if rssi is not None and (
                    entry["latest_rssi"] is None or rssi > entry["latest_rssi"]
                ):
                    entry["latest_rssi"] = rssi

            meta_rows = await self._db.fetch_all(
                f"""
                SELECT node_id, long_name, short_name, protocol
                FROM nodes
                WHERE node_id IN ({",".join("?" * len(node_ids))})
                """,
                tuple(sorted(node_ids)),
            )
            meta_by_id = {r["node_id"]: r for r in meta_rows}

            for nid in sorted(node_ids):
                meta = meta_by_id.get(nid, {})
                stats = count_by_id.get(nid, {})
                label = (
                    meta.get("long_name")
                    or meta.get("short_name")
                    or f"!{nid[-4:]}"
                )
                nodes.append({
                    "id": nid,
                    "label": label,
                    "protocol": meta.get("protocol")
                    or stats.get("protocol")
                    or "meshtastic",
                    "packet_count": int(stats.get("packet_count") or 0),
                    "latest_rssi": stats.get("latest_rssi"),
                })

        return {
            "hours": hours,
            "nodes": nodes,
            "edges": list(edges_by_key.values()),
            "routes": routes,
        }

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
            relay_node=row.get("relay_node", 0),
            decoded_payload=decoded,
            decrypted=bool(row.get("decrypted", 0)),
            signal=signal,
            capture_source=row.get("capture_source", "unknown"),
            timestamp=datetime.fromisoformat(row["timestamp"]),
        )
