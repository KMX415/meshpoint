"""Per-channel relay duty budget and throttle controls."""

from __future__ import annotations

import unittest

from src.models.packet import Packet, PacketType, Protocol
from src.models.signal import SignalMetrics
from src.relay.channel_budget import (
    ChannelBudget,
    effective_limit_percent,
    normalize_channel_throttle,
    resolve_relay_regulatory_ceiling,
)
from src.relay.relay_manager import RelayManager


def _relay_packet(
    *,
    source_id: str = "a3f2b1c0",
    packet_id: str = "pkt001",
    channel_hash: int = 0,
) -> Packet:
    return Packet(
        packet_id=packet_id,
        source_id=source_id,
        destination_id="ffffffff",
        protocol=Protocol.MESHTASTIC,
        packet_type=PacketType.TEXT,
        hop_limit=2,
        hop_start=3,
        channel_hash=channel_hash,
        signal=SignalMetrics(
            rssi=-95.0,
            snr=5.0,
            frequency_mhz=906.875,
            spreading_factor=11,
            bandwidth_khz=250.0,
        ),
    )


class TestChannelBudget(unittest.TestCase):
    def test_omitted_throttle_defaults_to_full_budget(self) -> None:
        budget = ChannelBudget(region="US", window_seconds=3600)
        toa = budget.estimate_packet_toa_ms(_relay_packet())
        self.assertTrue(budget.check_budget(0, toa))

    def test_fifty_percent_throttle_blocks_after_budget_exhausted(self) -> None:
        budget = ChannelBudget(
            throttle_percent={"0": 50},
            region="US",
            window_seconds=3600,
        )
        toa = budget.estimate_packet_toa_ms(_relay_packet())
        window_ms = 3600 * 1000
        max_ms = int(window_ms * 0.5)
        packets_to_fill = max(1, max_ms // max(toa, 1))

        for i in range(packets_to_fill):
            self.assertTrue(
                budget.check_budget(0, toa),
                f"packet {i} should fit in 50% budget",
            )
            budget.record_tx(0, toa)

        self.assertFalse(budget.check_budget(0, toa))

    def test_eu_regulatory_ceiling_caps_effective_limit(self) -> None:
        self.assertEqual(resolve_relay_regulatory_ceiling("EU_868"), 1.0)
        self.assertIsNone(resolve_relay_regulatory_ceiling("US"))
        self.assertEqual(
            effective_limit_percent(0, {"0": 100}, 1.0),
            1.0,
        )
        self.assertEqual(
            effective_limit_percent(0, {"0": 50}, 1.0),
            1.0,
        )

    def test_normalize_rejects_invalid_channel(self) -> None:
        with self.assertRaises(ValueError):
            normalize_channel_throttle({"99": 50})

    def test_summary_includes_all_channels(self) -> None:
        budget = ChannelBudget(throttle_percent={"1": 75}, region="US")
        summary = budget.summary()
        self.assertEqual(len(summary["channels"]), 8)
        self.assertEqual(summary["channels"][1]["throttle_percent"], 75)


class TestRelayManagerDutyCycle(unittest.TestCase):
    def test_channel_throttle_rejects_under_synthetic_load(self) -> None:
        manager = RelayManager(
            enabled=True,
            max_relay_per_minute=10_000,
            burst_size=10_000,
            channel_throttle_percent={"0": 50},
            region="US",
        )
        toa = manager._channel_budget.estimate_packet_toa_ms(_relay_packet())
        window_ms = 3600 * 1000
        max_ms = int(window_ms * 0.5)
        packets_to_fill = max(1, max_ms // max(toa, 1))

        for i in range(packets_to_fill):
            pkt = _relay_packet(packet_id=f"p{i}")
            decision = manager.evaluate(pkt)
            self.assertTrue(decision.should_relay, decision.reason)
            manager._channel_budget.record_packet(pkt)

        blocked = manager.evaluate(_relay_packet(packet_id="overflow"))
        self.assertFalse(blocked.should_relay)
        self.assertEqual(blocked.reason, "channel_throttled")

    def test_full_throttle_allows_more_than_fifty_percent(self) -> None:
        full = RelayManager(
            enabled=True,
            max_relay_per_minute=10_000,
            burst_size=10_000,
            channel_throttle_percent={},
            region="US",
        )
        half = RelayManager(
            enabled=True,
            max_relay_per_minute=10_000,
            burst_size=10_000,
            channel_throttle_percent={"0": 50},
            region="US",
        )
        toa = full._channel_budget.estimate_packet_toa_ms(_relay_packet())
        window_ms = 3600 * 1000
        half_max = int(window_ms * 0.5)
        packets_to_fill = max(1, half_max // max(toa, 1)) + 1

        for i in range(packets_to_fill):
            full._channel_budget.record_tx(0, toa)
            half._channel_budget.record_tx(0, toa)

        self.assertTrue(full._channel_budget.check_budget(0, toa))
        self.assertFalse(half._channel_budget.check_budget(0, toa))

    def test_reload_channel_budget_updates_throttle(self) -> None:
        manager = RelayManager(enabled=True, channel_throttle_percent={"0": 100})
        manager.reload_channel_budget(channel_throttle_percent={"0": 1})
        status = manager._channel_budget.channel_status(0)
        self.assertEqual(status["effective_limit_percent"], 1)


if __name__ == "__main__":
    unittest.main()
