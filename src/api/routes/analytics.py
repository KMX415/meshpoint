from __future__ import annotations

from fastapi import APIRouter

from src.analytics.signal_analyzer import SignalAnalyzer
from src.analytics.traffic_monitor import TrafficMonitor

router = APIRouter(prefix="/api/analytics", tags=["analytics"])

_signal_analyzer: SignalAnalyzer | None = None
_traffic_monitor: TrafficMonitor | None = None


def init_routes(
    signal_analyzer: SignalAnalyzer, traffic_monitor: TrafficMonitor
) -> None:
    global _signal_analyzer, _traffic_monitor
    _signal_analyzer = signal_analyzer
    _traffic_monitor = traffic_monitor


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
