from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from src.storage.packet_repository import PacketRepository

logger = logging.getLogger(__name__)


class TrafficMonitor:
    """Tracks packet rates, protocol distribution, and channel load."""

    def __init__(self, packet_repo: PacketRepository):
        self._packet_repo = packet_repo

    async def get_traffic_summary(self) -> dict:
        total = await self._packet_repo.get_count()
        now = datetime.now(timezone.utc)
        last_hour = await self._packet_repo.get_count_since(
            now - timedelta(hours=1)
        )
        last_minute = await self._packet_repo.get_count_since(
            now - timedelta(minutes=1)
        )
        protocol_dist = await self._packet_repo.get_protocol_distribution()
        type_dist = await self._packet_repo.get_type_distribution()

        return {
            "total_packets": total,
            "packets_last_hour": last_hour,
            "packets_last_minute": last_minute,
            "packets_per_minute": round(last_hour / 60.0, 1) if last_hour else 0,
            "protocol_distribution": protocol_dist,
            "type_distribution": type_dist,
        }

    async def get_recent_activity(
        self, minutes: int = 60, bucket_minutes: int = 5
    ) -> dict[str, list]:
        """Return packet counts bucketed by time for timeline charts."""
        packets = await self._packet_repo.get_recent(limit=2000)
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(minutes=minutes)

        buckets: list[str] = []
        counts: list[int] = []

        for i in range(0, minutes, bucket_minutes):
            bucket_start = cutoff + timedelta(minutes=i)
            bucket_end = bucket_start + timedelta(minutes=bucket_minutes)
            label = bucket_start.strftime("%H:%M")
            count = sum(
                1
                for p in packets
                if bucket_start <= p.timestamp < bucket_end
            )
            buckets.append(label)
            counts.append(count)

        return {"labels": buckets, "counts": counts}
