"""Unit tests for src/api/telemetry/noise_floor.py."""
from __future__ import annotations

import time
import unittest

from src.api.telemetry.noise_floor import (
    CALIBRATING_BELOW,
    MAX_SNR_FOR_FLOOR_DB,
    NOISE_FIGURE_DB,
    SOURCE_PACKETS,
    SOURCE_SPECTRAL,
    STALE_AFTER_SECONDS_PACKETS,
    NoiseFloorTracker,
    _theoretical_floor,
)


class TestTheoreticalFloor(unittest.TestCase):

    def test_125khz_floor_is_around_minus_117(self) -> None:
        floor = _theoretical_floor(125.0)
        # -174 + 10*log10(125e3) + 6 ~= -117 dBm
        self.assertIsNotNone(floor)
        self.assertAlmostEqual(floor, -117.0, delta=0.5)

    def test_250khz_floor_is_around_minus_114(self) -> None:
        floor = _theoretical_floor(250.0)
        self.assertAlmostEqual(floor, -114.0, delta=0.5)

    def test_500khz_floor_is_around_minus_111(self) -> None:
        floor = _theoretical_floor(500.0)
        self.assertAlmostEqual(floor, -111.0, delta=0.5)

    def test_zero_or_none_returns_none(self) -> None:
        self.assertIsNone(_theoretical_floor(0))
        self.assertIsNone(_theoretical_floor(None))


class TestNoiseFloorTracker(unittest.TestCase):

    def test_first_sample_records_raw_noise_value(self) -> None:
        tracker = NoiseFloorTracker()
        sample = tracker.update(rssi_dbm=-90, snr_db=5, bandwidth_khz=250)
        self.assertIsNotNone(sample)
        self.assertEqual(sample.noise_dbm, -95.0)

    def test_rolling_min_picks_lowest_observed_value(self) -> None:
        tracker = NoiseFloorTracker()
        tracker.update(rssi_dbm=-65, snr_db=7, bandwidth_khz=250)   # -72
        tracker.update(rssi_dbm=-95, snr_db=5, bandwidth_khz=250)   # -100
        tracker.update(rssi_dbm=-80, snr_db=2, bandwidth_khz=250)   # -82
        self.assertEqual(tracker.rolling_min, -100.0)


    def test_none_inputs_return_none(self) -> None:
        tracker = NoiseFloorTracker()
        self.assertIsNone(tracker.update(rssi_dbm=None, snr_db=5))
        self.assertIsNone(tracker.update(rssi_dbm=-90, snr_db=None))

    def test_nan_inputs_are_dropped(self) -> None:
        tracker = NoiseFloorTracker()
        self.assertIsNone(
            tracker.update(rssi_dbm=float("nan"), snr_db=5, bandwidth_khz=250)
        )

    def test_zero_snr_with_real_rssi_is_treated_as_unknown(self) -> None:
        # Encrypted Meshtastic packets sometimes set snr=0.0 as a placeholder;
        # we should drop those rather than report noise = rssi.
        tracker = NoiseFloorTracker()
        self.assertIsNone(
            tracker.update(rssi_dbm=-95, snr_db=0.0, bandwidth_khz=250)
        )

    def test_below_theoretical_floor_is_clamped(self) -> None:
        # 250 kHz floor is ~-114 dBm; -130 is below it and should be rejected.
        tracker = NoiseFloorTracker()
        self.assertIsNone(
            tracker.update(rssi_dbm=-128, snr_db=2, bandwidth_khz=250)
        )

    def test_buffer_bounded_to_capacity(self) -> None:
        tracker = NoiseFloorTracker(buffer_size=5)
        for i in range(20):
            tracker.update(rssi_dbm=-90 - i * 0.1, snr_db=5, bandwidth_khz=250)
        snap = tracker.snapshot()
        self.assertEqual(len(snap["samples_dbm"]), 5)

    def test_snapshot_value_is_rolling_min_when_only_packets_seen(self) -> None:
        tracker = NoiseFloorTracker()
        tracker.update(rssi_dbm=-65, snr_db=7, bandwidth_khz=250)   # -72
        tracker.update(rssi_dbm=-95, snr_db=8, bandwidth_khz=250)   # -103
        snap = tracker.snapshot()
        self.assertEqual(snap["bandwidth_khz"], 250)
        self.assertAlmostEqual(snap["theoretical_floor_dbm"], -114.0, delta=0.5)
        self.assertEqual(snap["value_dbm"], -103.0)
        self.assertEqual(snap["source"], SOURCE_PACKETS)
        self.assertFalse(snap["stale"])

    def test_snapshot_marks_stale_when_no_recent_sample(self) -> None:
        tracker = NoiseFloorTracker()
        old_ts = time.time() - (STALE_AFTER_SECONDS_PACKETS + 5)
        tracker.update(
            rssi_dbm=-90, snr_db=5, bandwidth_khz=250, timestamp=old_ts,
        )
        snap = tracker.snapshot()
        self.assertTrue(snap["stale"])

    def test_reset_clears_state(self) -> None:
        tracker = NoiseFloorTracker()
        tracker.update(rssi_dbm=-90, snr_db=5, bandwidth_khz=250)
        tracker.reset()
        snap = tracker.snapshot()
        self.assertIsNone(snap["value_dbm"])
        self.assertEqual(len(snap["samples_dbm"]), 0)
        self.assertTrue(snap["stale"])

    def test_unknown_bandwidth_uses_global_clamp(self) -> None:
        tracker = NoiseFloorTracker()
        # Without a bandwidth we accept any value in [-150, 0].
        self.assertIsNotNone(tracker.update(rssi_dbm=-90, snr_db=5))
        self.assertIsNone(tracker.update(rssi_dbm=-200, snr_db=5))


class TestSaturationGuardAndAcceptance(unittest.TestCase):
    """The tracker must accept strong packets so rural-mountain
    setups (one near neighbour, no weak traffic) get a number, while
    still rejecting samples whose SNR is at the demod register
    ceiling (which would underestimate the floor).
    """

    def test_strong_rssi_is_accepted(self) -> None:
        # Tower-Relay-style packet: -65 dBm, 7 dB SNR. Earlier
        # versions filtered these out and rural users got stuck on
        # "calibrating" forever. Now the rolling-min estimator
        # tolerates them; the upper bound just stays loose until a
        # weaker packet arrives.
        tracker = NoiseFloorTracker()
        sample = tracker.update(
            rssi_dbm=-65, snr_db=7, bandwidth_khz=250,
        )
        self.assertIsNotNone(sample)
        self.assertEqual(sample.noise_dbm, -72.0)

    def test_clipped_snr_is_rejected(self) -> None:
        # SNR at/above 18 dB is treated as likely-clipped on the
        # SX126x register (which saturates around +22 dB) and would
        # bias the floor estimate low.
        tracker = NoiseFloorTracker()
        self.assertIsNone(
            tracker.update(rssi_dbm=-50, snr_db=22, bandwidth_khz=250),
        )
        self.assertIsNone(
            tracker.update(rssi_dbm=-90, snr_db=18, bandwidth_khz=250),
        )

    def test_below_clip_threshold_still_accepted_at_strong_rssi(self) -> None:
        tracker = NoiseFloorTracker()
        sample = tracker.update(
            rssi_dbm=-50, snr_db=10, bandwidth_khz=250,
        )
        self.assertIsNotNone(sample)
        self.assertEqual(sample.noise_dbm, -60.0)

    def test_clip_threshold_matches_docstring(self) -> None:
        self.assertEqual(MAX_SNR_FOR_FLOOR_DB, 18.0)


class TestRollingMinConvergesAsWeakPacketsArrive(unittest.TestCase):
    """The whole point of the rolling-min approach: as more packets
    are heard (especially weaker ones), the estimate tightens
    toward the true noise floor without ever sticking on
    "calibrating" while real packets are arriving.
    """

    def test_strong_only_packets_yield_loose_estimate(self) -> None:
        tracker = NoiseFloorTracker()
        for _ in range(5):
            tracker.update(rssi_dbm=-65, snr_db=7, bandwidth_khz=250)
        self.assertEqual(tracker.rolling_min, -72.0)

    def test_arrival_of_weaker_packet_tightens_estimate(self) -> None:
        tracker = NoiseFloorTracker()
        for _ in range(5):
            tracker.update(rssi_dbm=-65, snr_db=7, bandwidth_khz=250)
        tracker.update(rssi_dbm=-100, snr_db=5, bandwidth_khz=250)
        self.assertEqual(tracker.rolling_min, -105.0)


class TestCalibratingFlag(unittest.TestCase):

    def test_calibrating_until_threshold_samples_collected(self) -> None:
        tracker = NoiseFloorTracker()
        # Use any accepted packet shape (strong or weak both work
        # now that the RSSI filter is gone).
        for _ in range(CALIBRATING_BELOW - 1):
            tracker.update(rssi_dbm=-65, snr_db=7, bandwidth_khz=250)
        snap = tracker.snapshot()
        self.assertTrue(snap["calibrating"])
        self.assertEqual(snap["samples_count"], CALIBRATING_BELOW - 1)

    def test_not_calibrating_once_enough_samples_collected(self) -> None:
        tracker = NoiseFloorTracker()
        for _ in range(CALIBRATING_BELOW):
            tracker.update(rssi_dbm=-65, snr_db=7, bandwidth_khz=250)
        snap = tracker.snapshot()
        self.assertFalse(snap["calibrating"])
        self.assertEqual(snap["samples_count"], CALIBRATING_BELOW)

    def test_calibrating_when_no_samples_yet(self) -> None:
        tracker = NoiseFloorTracker()
        snap = tracker.snapshot()
        self.assertTrue(snap["calibrating"])
        self.assertEqual(snap["samples_count"], 0)
        self.assertIsNone(snap["value_dbm"])


class TestNoiseFigureSanity(unittest.TestCase):
    """Defensive: the constants used in the formula match what's documented."""

    def test_noise_figure_constant_matches_doc(self) -> None:
        self.assertEqual(NOISE_FIGURE_DB, 6.0)


class TestSpectralSourcePreferred(unittest.TestCase):
    """When spectral-scan readings are present, they take precedence
    over packet-derived rolling-min, because they directly measure
    ambient channel power instead of bounding it from above."""

    def test_spectral_reading_wins_over_packet_history(self) -> None:
        tracker = NoiseFloorTracker()
        # Establish a packet-derived bound first; this is what the
        # old single-source tracker would have shown.
        tracker.update(rssi_dbm=-65, snr_db=7, bandwidth_khz=250)
        # Now feed a spectral scan and expect it to dominate.
        tracker.update_from_spectral(
            floor_dbm=-118.0,
            median_dbm=-115.0,
            frequency_hz=906_875_000,
            bandwidth_khz=250,
            samples=1024,
        )
        snap = tracker.snapshot()
        self.assertEqual(snap["source"], SOURCE_SPECTRAL)
        self.assertEqual(snap["value_dbm"], -118.0)
        self.assertEqual(snap["median_dbm"], -115.0)
        self.assertEqual(snap["frequency_hz"], 906_875_000)
        self.assertFalse(snap["calibrating"])

    def test_packet_fallback_when_no_spectral_reading(self) -> None:
        tracker = NoiseFloorTracker()
        tracker.update(rssi_dbm=-95, snr_db=5, bandwidth_khz=250)
        snap = tracker.snapshot()
        self.assertEqual(snap["source"], SOURCE_PACKETS)
        self.assertEqual(snap["value_dbm"], -100.0)

    def test_packet_fallback_when_spectral_reading_is_stale(self) -> None:
        tracker = NoiseFloorTracker()
        # Stale spectral reading from 10 minutes ago (way past the
        # 180-second stale threshold).
        tracker.update_from_spectral(
            floor_dbm=-118.0,
            median_dbm=-115.0,
            frequency_hz=906_875_000,
            bandwidth_khz=250,
            samples=1024,
            timestamp=time.time() - 600,
        )
        # Fresh packet sample should be picked instead.
        tracker.update(rssi_dbm=-95, snr_db=5, bandwidth_khz=250)
        snap = tracker.snapshot()
        self.assertEqual(snap["source"], SOURCE_PACKETS)
        self.assertEqual(snap["value_dbm"], -100.0)

    def test_spectral_history_is_buffered_for_sparkline(self) -> None:
        tracker = NoiseFloorTracker()
        for floor in (-118, -119, -117, -120):
            tracker.update_from_spectral(
                floor_dbm=floor,
                median_dbm=floor + 3,
                frequency_hz=906_875_000,
                bandwidth_khz=250,
                samples=1024,
            )
        snap = tracker.snapshot()
        self.assertEqual(snap["samples_count"], 4)
        self.assertEqual(snap["samples_dbm"], [-118.0, -119.0, -117.0, -120.0])


if __name__ == "__main__":
    unittest.main()
