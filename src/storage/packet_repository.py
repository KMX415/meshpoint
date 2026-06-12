from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone

from src.models.packet import Packet, PacketType, Protocol
from src.models.signal import SignalMetrics
from src.storage.database import DatabaseManager

logger = logging.getLogger(__name__)

_EDGE_PRIORITY = {
    "neighborinfo": 3,
    "routing": 2,
    "traceroute": 1,
}


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

    async def get_hourly_traffic(
        self,
        hours: int = 24,
        *,
        default_sf: int = 11,
        default_bw_khz: float = 250.0,
    ) -> tuple[list[dict], dict[str, list[dict]]]:
        """Hourly packet counts and modem buckets for ToA estimation.

        Returns:
            (count_rows, modem_buckets_by_hour) where count_rows has keys
            hour_start, meshtastic, meshcore, total; modem buckets are
            grouped per hour_start with sf, bw, packet_count, avg_payload.
        """
        hours = max(1, min(int(hours), 168))
        since = (
            datetime.now(timezone.utc) - timedelta(hours=hours)
        ).isoformat()

        count_rows = await self._db.fetch_all(
            """
            SELECT
              strftime('%Y-%m-%dT%H:00:00Z', timestamp) AS hour_start,
              SUM(CASE WHEN protocol = 'meshtastic' THEN 1 ELSE 0 END) AS meshtastic,
              SUM(CASE WHEN protocol = 'meshcore' THEN 1 ELSE 0 END) AS meshcore,
              COUNT(*) AS total
            FROM packets
            WHERE timestamp >= ?
            GROUP BY hour_start
            ORDER BY hour_start ASC
            """,
            (since,),
        )

        modem_rows = await self._db.fetch_all(
            """
            SELECT
              strftime('%Y-%m-%dT%H:00:00Z', timestamp) AS hour_start,
              COALESCE(NULLIF(spreading_factor, 0), ?) AS sf,
              COALESCE(NULLIF(bandwidth_khz, 0), ?) AS bw,
              COUNT(*) AS packet_count,
              AVG(
                CASE
                  WHEN LENGTH(COALESCE(decoded_payload, '')) < 20 THEN 20
                  ELSE LENGTH(COALESCE(decoded_payload, ''))
                END
              ) AS avg_payload
            FROM packets
            WHERE timestamp >= ?
            GROUP BY hour_start, sf, bw
            ORDER BY hour_start ASC
            """,
            (default_sf, default_bw_khz, since),
        )

        modem_by_hour: dict[str, list[dict]] = {}
        for row in modem_rows:
            hour = row["hour_start"]
            modem_by_hour.setdefault(hour, []).append(row)

        return count_rows, modem_by_hour

    async def get_signal_buckets(
        self,
        source_id: str,
        hours: float = 24,
        bucket_minutes: int = 15,
    ) -> list[dict]:
        """15-minute RSSI/SNR buckets for node-card sparklines."""
        bucket_minutes = max(1, min(int(bucket_minutes), 60))
        since = (
            datetime.now(timezone.utc) - timedelta(hours=hours)
        ).isoformat()

        rows = await self._db.fetch_all(
            """
            SELECT
              strftime('%Y-%m-%dT%H:', timestamp) ||
                printf('%02d:00Z',
                  (CAST(strftime('%M', timestamp) AS INTEGER) / ?) * ?)
                AS bucket_start,
              AVG(rssi) AS rssi_avg,
              AVG(snr) AS snr_avg,
              COUNT(*) AS packet_count
            FROM packets
            WHERE source_id = ? AND timestamp >= ? AND rssi IS NOT NULL
            GROUP BY bucket_start
            ORDER BY bucket_start ASC
            """,
            (bucket_minutes, bucket_minutes, source_id, since),
        )
        return [
            {
                "bucket": row["bucket_start"].replace("Z", "+00:00"),
                "rssi_avg": (
                    round(row["rssi_avg"], 1)
                    if row["rssi_avg"] is not None
                    else None
                ),
                "snr_avg": (
                    round(row["snr_avg"], 1)
                    if row["snr_avg"] is not None
                    else None
                ),
                "packet_count": int(row["packet_count"] or 0),
            }
            for row in rows
        ]

    @staticmethod
    def _normalize_node_id(node_id: str | int | None) -> str | None:
        if node_id is None:
            return None
        text = str(node_id).strip().lower().lstrip("!")
        if not text:
            return None
        if len(text) > 8:
            text = text[-8:]
        return text.zfill(8)

    @staticmethod
    def _edge_key(source: str, target: str) -> str:
        a, b = sorted((source, target))
        return f"{a}_{b}"

    @staticmethod
    def _upsert_topology_edge(
        edges_by_key: dict[str, dict],
        *,
        source: str,
        target: str,
        edge_type: str,
        last_seen: str,
        rssi: float | None = None,
        snr: float | None = None,
        neighbor_snr: float | None = None,
    ) -> None:
        if source == target:
            return
        link_key = PacketRepository._edge_key(source, target)
        confidence = "high" if edge_type == "neighborinfo" else "observed"
        weak = rssi is not None and rssi < -110
        incoming = {
            "source": source,
            "target": target,
            "edge_type": edge_type,
            "confidence": confidence,
            "rssi": round(rssi, 1) if rssi is not None else None,
            "snr": round(snr, 1) if snr is not None else None,
            "neighbor_snr": (
                round(neighbor_snr, 1) if neighbor_snr is not None else None
            ),
            "last_seen": last_seen,
            "weak": weak,
        }
        existing = edges_by_key.get(link_key)
        if existing is None:
            edges_by_key[link_key] = incoming
            return
        new_rank = _EDGE_PRIORITY.get(edge_type, 0)
        old_rank = _EDGE_PRIORITY.get(existing.get("edge_type", ""), 0)
        if new_rank > old_rank:
            edges_by_key[link_key] = incoming
        elif new_rank == old_rank and last_seen > existing.get("last_seen", ""):
            edges_by_key[link_key] = incoming

    @staticmethod
    def _edges_from_route_path(
        edges_by_key: dict[str, dict],
        route: list[str],
        *,
        edge_type: str,
        last_seen: str,
        rssi: float | None = None,
        snr: float | None = None,
        snr_hops: list[float] | None = None,
    ) -> None:
        if len(route) < 2:
            return
        for idx in range(len(route) - 1):
            hop_snr = None
            if snr_hops and idx < len(snr_hops):
                hop_snr = snr_hops[idx]
            PacketRepository._upsert_topology_edge(
                edges_by_key,
                source=route[idx],
                target=route[idx + 1],
                edge_type=edge_type,
                last_seen=last_seen,
                rssi=rssi,
                snr=hop_snr if hop_snr is not None else snr,
            )

    async def get_topology_graph(
        self,
        hours: float = 24,
        *,
        edge_limit: int = 1000,
        route_limit: int = 200,
    ) -> dict:
        """Build nodes, mesh edges, and TRACEROUTE paths for the graph tab."""
        hours = max(1.0, min(float(hours), 168.0))
        since = (
            datetime.now(timezone.utc) - timedelta(hours=hours)
        ).isoformat()

        edges_by_key: dict[str, dict] = {}

        ni_rows = await self._db.fetch_all(
            """
            SELECT source_id, decoded_payload, rssi, snr, timestamp
            FROM packets
            WHERE packet_type = 'neighborinfo'
              AND decoded_payload IS NOT NULL
              AND timestamp >= ?
            ORDER BY timestamp DESC
            LIMIT ?
            """,
            (since, edge_limit),
        )

        for row in ni_rows:
            source = self._normalize_node_id(row["source_id"])
            if not source:
                continue
            try:
                payload = json.loads(row["decoded_payload"])
            except (json.JSONDecodeError, TypeError):
                continue

            neighbors = payload.get("neighbors", [])
            if not isinstance(neighbors, list):
                continue

            for neighbor in neighbors:
                nid = neighbor.get("node_id") or neighbor.get("id")
                target = self._normalize_node_id(nid)
                if not target:
                    continue
                neighbor_snr = neighbor.get("snr")
                self._upsert_topology_edge(
                    edges_by_key,
                    source=source,
                    target=target,
                    edge_type="neighborinfo",
                    last_seen=row["timestamp"],
                    rssi=row.get("rssi"),
                    snr=row.get("snr"),
                    neighbor_snr=neighbor_snr,
                )

        route_rows = await self._db.fetch_all(
            """
            SELECT source_id, decoded_payload, rssi, snr, timestamp
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
            route_raw = payload.get("route")
            if not isinstance(route_raw, list) or len(route_raw) < 2:
                continue
            normalized = [
                nid for n in route_raw
                if (nid := self._normalize_node_id(n))
            ]
            if len(normalized) < 2:
                continue
            key = f"{row['source_id']}:{'-'.join(normalized)}"
            if key in seen_routes:
                continue
            seen_routes.add(key)
            routes.append({
                "source": self._normalize_node_id(row["source_id"]) or row["source_id"],
                "route": normalized,
                "last_seen": row["timestamp"],
            })
            snr_hops = payload.get("snr_towards")
            if not isinstance(snr_hops, list):
                snr_hops = None
            self._edges_from_route_path(
                edges_by_key,
                normalized,
                edge_type="traceroute",
                last_seen=row["timestamp"],
                rssi=row.get("rssi"),
                snr=row.get("snr"),
                snr_hops=snr_hops,
            )

        routing_rows = await self._db.fetch_all(
            """
            SELECT source_id, decoded_payload, rssi, snr, timestamp
            FROM packets
            WHERE packet_type = 'routing'
              AND decoded_payload IS NOT NULL
              AND timestamp >= ?
            ORDER BY timestamp DESC
            LIMIT ?
            """,
            (since, route_limit),
        )

        for row in routing_rows:
            try:
                payload = json.loads(row["decoded_payload"])
            except (json.JSONDecodeError, TypeError):
                continue
            for field in ("route_reply", "route_request"):
                route_raw = payload.get(field)
                if not isinstance(route_raw, list) or len(route_raw) < 2:
                    continue
                normalized = [
                    nid for n in route_raw
                    if (nid := self._normalize_node_id(n))
                ]
                if len(normalized) < 2:
                    continue
                self._edges_from_route_path(
                    edges_by_key,
                    normalized,
                    edge_type="routing",
                    last_seen=row["timestamp"],
                    rssi=row.get("rssi"),
                    snr=row.get("snr"),
                )

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

        edges = list(edges_by_key.values())
        edge_sources = sorted({e.get("edge_type", "unknown") for e in edges})
        by_type = {t: 0 for t in ("neighborinfo", "routing", "traceroute")}
        for edge in edges:
            et = edge.get("edge_type")
            if et in by_type:
                by_type[et] += 1

        return {
            "hours": hours,
            "nodes": nodes,
            "edges": edges,
            "routes": routes,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "edge_sources": edge_sources,
            "stats": {
                "neighborinfo_packets": len(ni_rows),
                "traceroute_packets": len(route_rows),
                "routing_packets": len(routing_rows),
                "edges_neighborinfo": by_type["neighborinfo"],
                "edges_routing": by_type["routing"],
                "edges_traceroute": by_type["traceroute"],
            },
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
