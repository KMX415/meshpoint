"""Tests for SpectralScanService scheduling and tracker integration.

The service is exercised against a fake wrapper that records the
requested frequency and returns a canned result. The asyncio loop
itself is driven with an explicit short interval so tests stay
deterministic.
"""
from __future__ import annotations

import asyncio
import time
import unittest
from typing import Optional

from src.api.telemetry.noise_floor import (
    NoiseFloorTracker,
    SOURCE_PACKETS,
    SOURCE_SPECTRAL,
)
from src.api.telemetry.spectral_scan_service import SpectralScanService
from src.hal.sx1302_spectral_scan import SpectralScanResult


class _FakeWrapper:
    """Stand-in for SX1302Wrapper that records calls."""

    def __init__(
        self,
        result: Optional[SpectralScanResult] = None,
        supported: bool = True,
    ) -> None:
        self._result = result
        self.spectral_scan_supported = supported
        self.calls: list[tuple[int, int]] = []

    def run_spectral_scan(
        self, frequency_hz: int, nb_scan: int = 1024,
    ) -> Optional[SpectralScanResult]:
        self.calls.append((frequency_hz, nb_scan))
        return self._result


def _result(floor_dbm: float = -118.0, median_dbm: float = -115.0):
    # Build a histogram whose median lands at median_dbm and whose
    # 10th percentile lands at floor_dbm. Uniform across 4 bins is
    # enough.
    levels = [int(floor_dbm), int(floor_dbm + 2),
              int(median_dbm), int(median_dbm + 2)]
    counts = (10, 10, 10, 10)
    levels_padded = tuple(levels + [0] * (35 - 4))
    counts_padded = tuple(list(counts) + [0] * (35 - 4))
    return SpectralScanResult(
        levels_dbm=levels_padded,
        counts=counts_padded,
        frequency_hz=906_875_000,
        nb_scan=1024,
        timestamp=time.time(),
    )


class TestServiceLifecycle(unittest.IsolatedAsyncioTestCase):

    async def test_first_scan_after_startup_delay_publishes_to_tracker(self) -> None:
        wrapper = _FakeWrapper(result=_result())
        tracker = NoiseFloorTracker()
        service = SpectralScanService(
            wrapper=wrapper, tracker=tracker,
            frequency_hz=906_875_000, bandwidth_khz=250,
            interval_seconds=5.0, startup_delay_seconds=0.01,
        )
        await service.start()
        await asyncio.sleep(0.1)
        await service.stop()

        self.assertGreaterEqual(wrapper.calls.__len__(), 1)
        self.assertEqual(wrapper.calls[0][0], 906_875_000)
        snap = tracker.snapshot()
        self.assertEqual(snap["source"], SOURCE_SPECTRAL)
        self.assertIsNotNone(snap["value_dbm"])

    async def test_unsupported_hal_no_ops_gracefully(self) -> None:
        wrapper = _FakeWrapper(result=None, supported=False)
        tracker = NoiseFloorTracker()
        service = SpectralScanService(
            wrapper=wrapper, tracker=tracker,
            frequency_hz=906_875_000, bandwidth_khz=250,
            interval_seconds=5.0, startup_delay_seconds=0.01,
        )
        await service.start()
        await asyncio.sleep(0.05)
        await service.stop()

        self.assertEqual(wrapper.calls, [])
        # Tracker is empty; snapshot stays in packet-fallback mode.
        snap = tracker.snapshot()
        self.assertEqual(snap["source"], SOURCE_PACKETS)
        self.assertIsNone(snap["value_dbm"])

    async def test_failed_scan_increments_failure_counter(self) -> None:
        wrapper = _FakeWrapper(result=None, supported=True)
        tracker = NoiseFloorTracker()
        service = SpectralScanService(
            wrapper=wrapper, tracker=tracker,
            frequency_hz=906_875_000, bandwidth_khz=250,
            interval_seconds=5.0, startup_delay_seconds=0.01,
        )
        await service.start()
        await asyncio.sleep(0.1)
        await service.stop()

        self.assertGreaterEqual(service.scans_failed, 1)
        self.assertEqual(service.scans_run, 0)

    async def test_minimum_interval_clamped_to_5_seconds(self) -> None:
        wrapper = _FakeWrapper(result=_result(), supported=True)
        tracker = NoiseFloorTracker()
        service = SpectralScanService(
            wrapper=wrapper, tracker=tracker,
            frequency_hz=906_875_000, bandwidth_khz=250,
            interval_seconds=0.1, startup_delay_seconds=0.01,
        )
        # We can't directly observe the clamp without timing-flake,
        # but we can confirm the service does not spam scans more
        # than once in a short window.
        await service.start()
        await asyncio.sleep(0.2)
        await service.stop()
        self.assertLessEqual(len(wrapper.calls), 2)


if __name__ == "__main__":
    unittest.main()
