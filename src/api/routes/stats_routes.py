"""Local stats summary endpoint for the Stats dashboard tab.

Aggregates data from the in-memory StatsReporter, SQLite repositories,
and analytics classes into a single JSON response that matches the
richness of the cloud per-Meshpoint stats page.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Query

from src.analytics.network_mapper import NetworkMapper
from src.analytics.toa_estimate import sum_hourly_toa_ms
from src.analytics.signal_analyzer import SignalAnalyzer
from src.analytics.stats_reporter import StatsReporter
from src.analytics.traffic_monitor import TrafficMonitor
from src.relay.relay_manager import RelayManager
from src.config import load_config
from src.storage.node_repository import NodeRepository
from src.storage.packet_repository import PacketRepository
from src.version import __version__

router = APIRouter(prefix="/api/stats", tags=["stats"])

_start_time: datetime | None = None

_stats_reporter: StatsReporter | None = None
_signal_analyzer: SignalAnalyzer | None = None
_traffic_monitor: TrafficMonitor | None = None
_network_mapper: NetworkMapper | None = None
_relay_manager: RelayManager | None = None
_node_repo: NodeRepository | None = None
_packet_repo: PacketRepository | None = None


def init_routes(
    stats_reporter: StatsReporter,
    signal_analyzer: SignalAnalyzer,
    traffic_monitor: TrafficMonitor,
    network_mapper: NetworkMapper,
    relay_manager: RelayManager,
    node_repo: NodeRepository,
    packet_repo: PacketRepository,
) -> None:
    global _stats_reporter, _signal_analyzer, _traffic_monitor
    global _network_mapper, _relay_manager, _node_repo, _packet_repo
    global _start_time
    _stats_reporter = stats_reporter
    _signal_analyzer = signal_analyzer
    _traffic_monitor = traffic_monitor
    _network_mapper = network_mapper
    _relay_manager = relay_manager
    _node_repo = node_repo
    _packet_repo = packet_repo
    _start_time = datetime.now(timezone.utc)


@router.get("/summary")
async def stats_summary():
    """Comprehensive stats for the local Stats tab."""
    report = _stats_reporter.build_report() if _stats_reporter else {}
    signal = await _signal_analyzer.get_signal_summary() if _signal_analyzer else {}
    traffic = await _traffic_monitor.get_traffic_summary() if _traffic_monitor else {}
    timeline = (
        await _traffic_monitor.get_recent_activity(minutes=60, bucket_minutes=5)
        if _traffic_monitor else {"labels": [], "counts": []}
    )
    network = await _network_mapper.get_network_summary() if _network_mapper else {}
    relay = _relay_manager.get_stats() if _relay_manager else {}
    rssi_dist = await _signal_analyzer.get_rssi_distribution() if _signal_analyzer else {}
    snr_dist = await _signal_analyzer.get_snr_distribution() if _signal_analyzer else {}

    roles = await _get_role_distribution()
    hw_models = await _get_hw_model_distribution()
    active_24h = await _node_repo.get_active_count(24) if _node_repo else 0
    total_nodes = await _node_repo.get_count() if _node_repo else 0
    best_signal = await _get_best_signal()
    direct_relayed = await _get_direct_relayed_counts()
    farthest_mesh = await _get_farthest_via_mesh()

    device_ctx = _get_device_context()
    first_pkt = await _get_first_packet_time()

    return {
        "device": device_ctx,
        "first_packet_time": first_pkt,
        "live": report,
        "signal": {
            **signal,
            "best_rssi": best_signal.get("best_rssi"),
            "best_snr": best_signal.get("best_snr"),
        },
        "rssi_distribution": rssi_dist,
        "snr_distribution": snr_dist,
        "traffic": traffic,
        "traffic_timeline": timeline,
        "network": {
            **network,
            "roles": roles,
            "hw_models": hw_models,
            "active_24h": active_24h,
            "total_nodes": total_nodes,
        },
        "relay": relay,
        "direct_relayed": direct_relayed,
        "farthest_mesh": farthest_mesh,
    }


@router.get("/hourly")
async def stats_hourly(hours: int = Query(24, ge=1, le=168)):
    """SQL-backed hourly traffic buckets for the 24h Stats chart."""
    if not _packet_repo:
        return {"hours": hours, "region": "US", "buckets": []}

    try:
        config = load_config()
        radio = config.radio
        region = radio.region or "US"
        default_sf = radio.spreading_factor
        default_bw = radio.bandwidth_khz
        preamble = radio.preamble_length
    except Exception:
        region = "US"
        default_sf = 11
        default_bw = 250.0
        preamble = 16

    count_rows, modem_by_hour = await _packet_repo.get_hourly_traffic(
        hours,
        default_sf=default_sf,
        default_bw_khz=default_bw,
    )
    counts_by_hour = {row["hour_start"]: row for row in count_rows}

    now = datetime.now(timezone.utc)
    end_hour = now.replace(minute=0, second=0, microsecond=0)
    hour_ms = 3_600_000

    buckets = []
    for offset in range(hours - 1, -1, -1):
        hour_dt = end_hour - timedelta(hours=offset)
        hour_key = hour_dt.strftime("%Y-%m-%dT%H:00:00Z")
        counts = counts_by_hour.get(hour_key, {})
        modem_buckets = modem_by_hour.get(hour_key, [])
        toa_ms = sum_hourly_toa_ms(
            modem_buckets,
            default_sf=default_sf,
            default_bw_khz=default_bw,
            default_preamble=preamble,
        )
        duty_pct = round((toa_ms / hour_ms) * 100, 2) if hour_ms else 0.0
        buckets.append({
            "hour": hour_key.replace("Z", "+00:00"),
            "meshtastic": int(counts.get("meshtastic") or 0),
            "meshcore": int(counts.get("meshcore") or 0),
            "total": int(counts.get("total") or 0),
            "toa_ms_estimated": toa_ms,
            "duty_cycle_pct": duty_pct,
        })

    return {"hours": hours, "region": region, "buckets": buckets}


def _get_device_context() -> dict:
    try:
        config = load_config()
        name = config.device.device_name or "Meshpoint"
        region = config.radio.region or "US"
    except Exception:
        name = "Meshpoint"
        region = "US"

    uptime_s = 0
    if _start_time:
        uptime_s = int((datetime.now(timezone.utc) - _start_time).total_seconds())
    days_online = max(1, uptime_s // 86400) if uptime_s > 0 else 0

    return {
        "name": name,
        "region": region,
        "firmware": __version__,
        "uptime_seconds": uptime_s,
        "days_online": days_online,
    }


async def _get_first_packet_time() -> str | None:
    if not _packet_repo:
        return None
    row = await _packet_repo._db.fetch_one(
        "SELECT MIN(timestamp) as first_ts FROM packets"
    )
    if row and row["first_ts"]:
        return row["first_ts"]
    return None


async def _get_role_distribution() -> dict[str, int]:
    if not _node_repo:
        return {}
    rows = await _node_repo._db.fetch_all(
        "SELECT role, COUNT(*) as cnt FROM nodes "
        "WHERE role IS NOT NULL GROUP BY role"
    )
    return {r["role"]: r["cnt"] for r in rows}


async def _get_hw_model_distribution() -> dict[str, int]:
    if not _node_repo:
        return {}
    rows = await _node_repo._db.fetch_all(
        "SELECT hardware_model, COUNT(*) as cnt FROM nodes "
        "WHERE hardware_model IS NOT NULL GROUP BY hardware_model"
    )
    return {r["hardware_model"]: r["cnt"] for r in rows}


async def _get_best_signal() -> dict:
    if not _packet_repo:
        return {}
    row = await _packet_repo._db.fetch_one(
        "SELECT MAX(rssi) as best_rssi, MAX(snr) as best_snr "
        "FROM packets WHERE rssi IS NOT NULL AND rssi < 0"
    )
    if not row:
        return {}
    return {
        "best_rssi": round(row["best_rssi"], 1) if row["best_rssi"] is not None else None,
        "best_snr": round(row["best_snr"], 1) if row["best_snr"] is not None else None,
    }


async def _get_direct_relayed_counts() -> dict:
    if not _packet_repo:
        return {"direct": 0, "relayed": 0}
    row = await _packet_repo._db.fetch_one(
        """
        SELECT
            SUM(CASE WHEN hop_start > 0 AND (hop_start - hop_limit) = 0 THEN 1
                     WHEN hop_start = 0 THEN 1 ELSE 0 END) as direct,
            SUM(CASE WHEN hop_start > 0 AND (hop_start - hop_limit) > 0 THEN 1
                     ELSE 0 END) as relayed
        FROM packets
        """
    )
    if not row:
        return {"direct": 0, "relayed": 0}
    return {
        "direct": row["direct"] or 0,
        "relayed": row["relayed"] or 0,
    }


async def _get_farthest_via_mesh() -> dict | None:
    """Find the farthest node reached via relay (1+ hops)."""
    if not _packet_repo or not _node_repo:
        return None
    rows = await _packet_repo._db.fetch_all(
        """
        SELECT DISTINCT p.source_id, n.long_name, n.latitude, n.longitude
        FROM packets p
        JOIN nodes n ON p.source_id = n.node_id
        WHERE p.hop_start > 0 AND (p.hop_start - p.hop_limit) > 0
          AND n.latitude IS NOT NULL AND n.longitude IS NOT NULL
        """,
    )
    if not rows:
        return None

    from src.analytics.stats_reporter import _haversine_mi
    from src.config import load_config

    try:
        config = load_config()
        dev_lat = config.device.latitude
        dev_lon = config.device.longitude
    except Exception:
        return None

    if dev_lat is None or dev_lon is None:
        return None

    best = None
    for r in rows:
        dist = _haversine_mi(dev_lat, dev_lon, r["latitude"], r["longitude"])
        if dist < 0.1:
            continue
        if best is None or dist > best["miles"]:
            best = {
                "miles": round(dist, 1),
                "node_id": r["source_id"],
                "node_name": r["long_name"] or r["source_id"],
            }
    return best
