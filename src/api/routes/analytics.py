from __future__ import annotations

from fastapi import APIRouter, Query

from src.analytics.signal_analyzer import SignalAnalyzer
from src.analytics.traffic_monitor import TrafficMonitor
from src.storage.packet_repository import PacketRepository

router = APIRouter(prefix="/api/analytics", tags=["analytics"])

_signal_analyzer: SignalAnalyzer | None = None
_traffic_monitor: TrafficMonitor | None = None
_packet_repo: PacketRepository | None = None


def init_routes(
    signal_analyzer: SignalAnalyzer,
    traffic_monitor: TrafficMonitor,
    packet_repo: PacketRepository | None = None,
) -> None:
    global _signal_analyzer, _traffic_monitor, _packet_repo
    _signal_analyzer = signal_analyzer
    _traffic_monitor = traffic_monitor
    _packet_repo = packet_repo


@router.get("/traffic")
async def traffic_summary():
    return await _traffic_monitor.get_traffic_summary()


@router.get("/traffic/timeline")
async def traffic_timeline(minutes: int = 60, bucket_minutes: int = 5):
    return await _traffic_monitor.get_recent_activity(minutes, bucket_minutes)


@router.get("/signal/rssi")
async def rssi_distribution():
    return await _signal_analyzer.get_rssi_distribution()


@router.get("/signal/snr")
async def snr_distribution():
    return await _signal_analyzer.get_snr_distribution()


@router.get("/signal/summary")
async def signal_summary():
    return await _signal_analyzer.get_signal_summary()


@router.get("/topology")
async def network_topology(hours: float = Query(24, ge=1, le=168)):
    """Mesh graph data from NEIGHBORINFO edges and TRACEROUTE paths."""
    if not _packet_repo:
        return {"hours": hours, "nodes": [], "edges": [], "routes": []}

    return await _packet_repo.get_topology_graph(hours)
