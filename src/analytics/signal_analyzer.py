from __future__ import annotations

import logging

from src.storage.packet_repository import PacketRepository

logger = logging.getLogger(__name__)


class SignalAnalyzer:
    """Analyzes RSSI/SNR distributions and signal quality trends."""

    def __init__(self, packet_repo: PacketRepository):
        self._packet_repo = packet_repo

    async def get_rssi_distribution(
        self, limit: int = 500
    ) -> dict[str, list]:
        """Return RSSI values bucketed for histogram display."""
        packets = await self._packet_repo.get_recent(limit)
        values = [
            p.signal.rssi for p in packets if p.signal is not None
        ]
        if not values:
            return {"buckets": [], "counts": []}

        bucket_size = 5
        min_rssi = int(min(values) // bucket_size) * bucket_size
        max_rssi = int(max(values) // bucket_size + 1) * bucket_size

        buckets = list(range(min_rssi, max_rssi + bucket_size, bucket_size))
        counts = [0] * len(buckets)

        for v in values:
            idx = int((v - min_rssi) // bucket_size)
            idx = min(idx, len(counts) - 1)
            counts[idx] += 1

        return {
            "buckets": [f"{b}" for b in buckets],
            "counts": counts,
        }

    async def get_snr_distribution(
        self, limit: int = 500
    ) -> dict[str, list]:
        packets = await self._packet_repo.get_recent(limit)
        values = [
            p.signal.snr for p in packets if p.signal is not None
        ]
        if not values:
            return {"buckets": [], "counts": []}

        bucket_size = 2
        min_snr = int(min(values) // bucket_size) * bucket_size
        max_snr = int(max(values) // bucket_size + 1) * bucket_size

        buckets = list(range(min_snr, max_snr + bucket_size, bucket_size))
        counts = [0] * len(buckets)

        for v in values:
            idx = int((v - min_snr) // bucket_size)
            idx = min(idx, len(counts) - 1)
            counts[idx] += 1

        return {
            "buckets": [f"{b}" for b in buckets],
            "counts": counts,
        }

    async def get_signal_summary(self) -> dict:
        packets = await self._packet_repo.get_recent(200)
        rssi_vals = [p.signal.rssi for p in packets if p.signal]
        snr_vals = [p.signal.snr for p in packets if p.signal]

        if not rssi_vals:
            return {"avg_rssi": None, "avg_snr": None, "sample_count": 0}

        return {
            "avg_rssi": round(sum(rssi_vals) / len(rssi_vals), 1),
            "min_rssi": round(min(rssi_vals), 1),
            "max_rssi": round(max(rssi_vals), 1),
            "avg_snr": round(sum(snr_vals) / len(snr_vals), 1),
            "sample_count": len(rssi_vals),
        }
