"""Prometheus-compatible metrics scrape endpoint (PR 09).

Zero-dependency text exposition format. Disabled by default via
``metrics.enabled`` in config.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import PlainTextResponse

from src.config import MetricsConfig
from src.version import __version__

if TYPE_CHECKING:
    from src.analytics.signal_analyzer import SignalAnalyzer
    from src.analytics.stats_reporter import StatsReporter
    from src.analytics.traffic_monitor import TrafficMonitor
    from src.api.telemetry.noise_floor import NoiseFloorTracker
    from src.capture.capture_coordinator import CaptureCoordinator
    from src.relay.relay_manager import RelayManager
    from src.storage.node_repository import NodeRepository

router = APIRouter(tags=["metrics"])

_config: MetricsConfig | None = None
_start_time: datetime | None = None
_stats_reporter: StatsReporter | None = None
_signal_analyzer: SignalAnalyzer | None = None
_traffic_monitor: TrafficMonitor | None = None
_relay_manager: RelayManager | None = None
_node_repo: NodeRepository | None = None
_noise_floor_tracker: NoiseFloorTracker | None = None
_capture_coordinator: CaptureCoordinator | None = None
_region: str = "US"


def init_routes(
    *,
    metrics_config: MetricsConfig,
    stats_reporter: StatsReporter,
    signal_analyzer: SignalAnalyzer,
    traffic_monitor: TrafficMonitor,
    relay_manager: RelayManager,
    node_repo: NodeRepository,
    noise_floor_tracker: NoiseFloorTracker,
    capture_coordinator: CaptureCoordinator,
    region: str,
) -> None:
    global _config, _start_time, _stats_reporter, _signal_analyzer
    global _traffic_monitor, _relay_manager, _node_repo
    global _noise_floor_tracker, _capture_coordinator, _region
    _config = metrics_config
    _start_time = datetime.now(timezone.utc)
    _stats_reporter = stats_reporter
    _signal_analyzer = signal_analyzer
    _traffic_monitor = traffic_monitor
    _relay_manager = relay_manager
    _node_repo = node_repo
    _noise_floor_tracker = noise_floor_tracker
    _capture_coordinator = capture_coordinator
    _region = region or "US"


@router.get("/metrics")
async def prometheus_metrics(
    request: Request,
    authorization: str | None = Header(default=None),
) -> PlainTextResponse:
    if _config is None or not _config.enabled:
        raise HTTPException(status_code=404, detail="metrics disabled")

    if _config.require_auth:
        from src.api.auth.dependencies import require_auth

        await require_auth(request, authorization)

    body = await _render_metrics()
    return PlainTextResponse(
        body,
        media_type="text/plain; version=0.0.4; charset=utf-8",
    )


async def _render_metrics() -> str:
    writer = PrometheusWriter()
    uptime = _uptime_seconds()
    writer.gauge(
        "meshpoint_uptime_seconds",
        uptime,
        help="Seconds since the metrics collector started",
    )
    writer.gauge(
        "meshpoint_info",
        1,
        labels={"version": __version__, "region": _region},
        help="Meshpoint build info (always 1)",
    )

    if _stats_reporter is not None:
        report = _stats_reporter.build_report()
        writer.counter(
            "meshpoint_packets_session_total",
            report.get("total_packets", 0),
            help="Decoded packets since last heartbeat reset",
        )
        writer.gauge(
            "meshpoint_packets_per_minute",
            report.get("packets_per_minute", 0),
            help="Session packet rate (packets per minute)",
        )
        for protocol, count in (report.get("protocols") or {}).items():
            writer.counter(
                "meshpoint_protocol_packets_session_total",
                count,
                labels={"protocol": _safe_label(protocol)},
                help="Session packets by protocol",
            )
        rssi_count = report.get("rssi_count") or 0
        if rssi_count:
            writer.gauge(
                "meshpoint_rssi_average_dbm",
                round(report["rssi_sum"] / rssi_count, 2),
                help="Average RSSI over session samples",
            )
        snr_count = report.get("snr_count") or 0
        if snr_count:
            writer.gauge(
                "meshpoint_snr_average_db",
                round(report["snr_sum"] / snr_count, 2),
                help="Average SNR over session samples",
            )
        writer.counter(
            "meshpoint_packets_direct_session_total",
            report.get("direct_count", 0),
            help="Direct (0-hop) packets in session",
        )
        writer.counter(
            "meshpoint_packets_relayed_session_total",
            report.get("relayed_count", 0),
            help="Relayed (1+ hop) packets in session",
        )

    if _traffic_monitor is not None:
        traffic = await _traffic_monitor.get_traffic_summary()
        writer.counter(
            "meshpoint_packets_database_total",
            traffic.get("total_packets", 0),
            help="Total packets stored in SQLite",
        )
        writer.gauge(
            "meshpoint_packets_last_hour",
            traffic.get("packets_last_hour", 0),
            help="Packets received in the last hour",
        )
        writer.gauge(
            "meshpoint_packets_last_minute",
            traffic.get("packets_last_minute", 0),
            help="Packets received in the last minute",
        )

    if _signal_analyzer is not None:
        signal = await _signal_analyzer.get_signal_summary()
        if signal.get("avg_rssi") is not None:
            writer.gauge(
                "meshpoint_rssi_recent_average_dbm",
                signal["avg_rssi"],
                help="Average RSSI over the 200 most recent packets",
            )
        if signal.get("avg_snr") is not None:
            writer.gauge(
                "meshpoint_snr_recent_average_db",
                signal["avg_snr"],
                help="Average SNR over the 200 most recent packets",
            )

    if _node_repo is not None:
        writer.gauge(
            "meshpoint_nodes_total",
            await _node_repo.get_count(),
            help="Known nodes in the local database",
        )
        writer.gauge(
            "meshpoint_nodes_active_24h",
            await _node_repo.get_active_count(24),
            help="Nodes heard in the last 24 hours",
        )

    if _noise_floor_tracker is not None:
        floor = _noise_floor_tracker.snapshot()
        value = floor.get("value_dbm")
        if value is not None:
            writer.gauge(
                "meshpoint_noise_floor_dbm",
                value,
                labels={"source": _safe_label(floor.get("source") or "unknown")},
                help="Estimated noise floor (dBm)",
            )
        writer.gauge(
            "meshpoint_noise_floor_stale",
            1 if floor.get("stale") else 0,
            help="1 when the noise-floor estimate is stale",
        )

    if _relay_manager is not None:
        relay = _relay_manager.get_stats()
        writer.gauge(
            "meshpoint_relay_enabled",
            1 if relay.get("enabled") else 0,
            help="1 when experimental relay is enabled",
        )
        writer.counter(
            "meshpoint_relay_relayed_total",
            relay.get("relayed", 0),
            help="Packets relayed since process start",
        )
        writer.counter(
            "meshpoint_relay_rejected_total",
            relay.get("rejected", 0),
            help="Packets rejected by relay filters",
        )
        for reason, count in (relay.get("rejection_reasons") or {}).items():
            writer.counter(
                "meshpoint_relay_rejected_total",
                count,
                labels={"reason": _safe_label(reason)},
                help="Relay rejections by reason",
            )
        writer.gauge(
            "meshpoint_relay_rate_per_minute",
            relay.get("current_rate", 0),
            help="Current relay rate (packets per minute)",
        )
        writer.gauge(
            "meshpoint_relay_rate_remaining",
            relay.get("rate_remaining", 0),
            help="Remaining relay capacity in the current window",
        )
        budget = relay.get("channel_budget") or {}
        writer.gauge(
            "meshpoint_relay_duty_usage_percent",
            budget.get("relay_total_usage_percent", 0),
            help="Aggregate relay duty usage (ToA estimate)",
        )
        for channel in budget.get("channels") or []:
            ch = channel.get("channel")
            if ch is None:
                continue
            writer.gauge(
                "meshpoint_relay_duty_channel_usage_percent",
                channel.get("usage_percent", 0),
                labels={"channel": str(ch)},
                help="Per-channel relay duty usage (ToA estimate)",
            )

    if _capture_coordinator is not None:
        rx = _capture_coordinator.concentrator_rx_stats()
        writer.counter(
            "meshpoint_rx_crc_bad_total",
            rx.get("crc_bad_total", 0),
            help="SX1302 CRC_BAD frames since concentrator start",
        )
        writer.counter(
            "meshpoint_rx_no_crc_total",
            rx.get("no_crc_total", 0),
            help="SX1302 NO_CRC frames since concentrator start",
        )

    return writer.render()


def _uptime_seconds() -> int:
    if _start_time is None:
        return 0
    return int((datetime.now(timezone.utc) - _start_time).total_seconds())


def _safe_label(value: str) -> str:
    """Restrict labels to safe alphanumeric tokens (no secrets)."""
    cleaned = "".join(
        ch if ch.isalnum() or ch in "-_" else "_"
        for ch in str(value).strip()
    )
    return cleaned[:64] or "unknown"


class PrometheusWriter:
    """Minimal Prometheus text 0.0.4 writer (no external deps)."""

    def __init__(self) -> None:
        self._lines: list[str] = []
        self._declared: set[tuple[str, str]] = set()

    def gauge(
        self,
        name: str,
        value: int | float,
        *,
        labels: dict[str, str] | None = None,
        help: str = "",
    ) -> None:
        self._emit(name, "gauge", value, labels=labels, help=help)

    def counter(
        self,
        name: str,
        value: int | float,
        *,
        labels: dict[str, str] | None = None,
        help: str = "",
    ) -> None:
        self._emit(name, "counter", value, labels=labels, help=help)

    def _emit(
        self,
        name: str,
        metric_type: str,
        value: int | float,
        *,
        labels: dict[str, str] | None,
        help: str,
    ) -> None:
        key = (name, metric_type)
        if key not in self._declared:
            if help:
                self._lines.append(f"# HELP {name} {help}")
            self._lines.append(f"# TYPE {name} {metric_type}")
            self._declared.add(key)

        label_str = _format_labels(labels)
        if isinstance(value, float):
            rendered = f"{value:.6g}"
        else:
            rendered = str(int(value))
        self._lines.append(f"{name}{label_str} {rendered}")

    def render(self) -> str:
        return "\n".join(self._lines) + "\n"


def _format_labels(labels: dict[str, str] | None) -> str:
    if not labels:
        return ""
    parts = [
        f'{_escape_label(k)}="{_escape_label(v)}"'
        for k, v in sorted(labels.items())
    ]
    return "{" + ",".join(parts) + "}"


def _escape_label(value: str) -> str:
    return (
        str(value)
        .replace("\\", "\\\\")
        .replace("\n", "\\n")
        .replace('"', '\\"')
    )
