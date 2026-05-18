"""Noise floor tracker.

Two-source estimator:

1. Primary: SX1302 spectral scan (when available)
   The concentrator's built-in spectral scanner samples the channel
   RSSI directly and returns a histogram across 35 levels. We use
   the median of that histogram as the canonical noise floor. This
   is what dedicated single-channel monitors (e.g. SX1262 HAT-based
   tools like pyMC) report on the same channel.

2. Fallback: per-packet ``rssi - snr`` rolling minimum
   For installations where spectral scan is unavailable (older HAL
   builds, hardware quirk), we fall back to the previous estimator:
   for any successfully decoded packet, ``rssi - snr`` is an upper
   bound on the actual noise floor, so the rolling minimum across
   recent packets converges toward it. This is loose in practice
   (especially in environments with only strong nearby neighbours)
   but is better than nothing.

The snapshot frame indicates which source produced the current
value via the ``source`` field (``"spectral_scan"`` or ``"packets"``)
so the UI can adjust its tooltip and trust level accordingly.

Saturation guard (fallback path only):
    The SX126x demod's SNR register clips around +22 dB. Packets
    with SNR >= 18 dB are likely clipped and would underestimate
    the noise floor; we drop those.

Sanity clamp:
    Theoretical thermal floor ``N0 = -174 + 10*log10(BW_Hz) + NF``
    sits around -117/-114/-111 dBm at 125/250/500 kHz with a 6 dB
    receiver NF. Samples below the floor (minus 3 dB slack) are
    physically impossible and dropped.

This class is sync and lock-free; the FastAPI app holds a single
instance and feeds it from packet callbacks and (when wired) a
spectral scan service.
"""
from __future__ import annotations

import math
import time
from collections import deque
from dataclasses import dataclass

DEFAULT_BUFFER_SIZE: int = 120
STALE_AFTER_SECONDS_PACKETS: float = 30.0
STALE_AFTER_SECONDS_SPECTRAL: float = 180.0
NOISE_FIGURE_DB: float = 6.0

MAX_SNR_FOR_FLOOR_DB: float = 18.0
CALIBRATING_BELOW: int = 3

SOURCE_SPECTRAL: str = "spectral_scan"
SOURCE_PACKETS: str = "packets"


@dataclass(slots=True)
class NoiseSample:
    """One per-packet noise estimate (fallback path)."""

    timestamp: float
    noise_dbm: float
    bandwidth_khz: float


@dataclass(slots=True)
class SpectralSnapshot:
    """One spectral-scan reading. The primary source when available."""

    timestamp: float
    floor_dbm: float
    median_dbm: float
    frequency_hz: int
    bandwidth_khz: float
    samples: int


class NoiseFloorTracker:
    """Two-source noise floor estimator: spectral scan primary, packets fallback."""

    def __init__(
        self,
        buffer_size: int = DEFAULT_BUFFER_SIZE,
    ) -> None:
        self._packet_buffer: deque[NoiseSample] = deque(maxlen=buffer_size)
        self._packet_last_at: float | None = None
        self._packet_bandwidth_khz: float | None = None

        self._spectral_history: deque[SpectralSnapshot] = deque(maxlen=64)
        self._spectral_last: SpectralSnapshot | None = None

    def update(
        self,
        rssi_dbm: float | None,
        snr_db: float | None,
        bandwidth_khz: float | None = None,
        timestamp: float | None = None,
    ) -> NoiseSample | None:
        """Push a per-packet sample (fallback path)."""
        if rssi_dbm is None or snr_db is None:
            return None
        if not math.isfinite(rssi_dbm) or not math.isfinite(snr_db):
            return None
        if snr_db == 0.0 and rssi_dbm < -50:
            return None
        if snr_db >= MAX_SNR_FOR_FLOOR_DB:
            return None

        sample_dbm = rssi_dbm - snr_db
        if not _is_physically_plausible(sample_dbm, bandwidth_khz):
            return None

        ts = timestamp if timestamp is not None else time.time()
        sample = NoiseSample(
            timestamp=ts,
            noise_dbm=sample_dbm,
            bandwidth_khz=bandwidth_khz or 0.0,
        )
        self._packet_buffer.append(sample)
        if bandwidth_khz:
            self._packet_bandwidth_khz = bandwidth_khz
        self._packet_last_at = ts
        return sample

    def update_from_spectral(
        self,
        floor_dbm: float,
        median_dbm: float,
        frequency_hz: int,
        bandwidth_khz: float,
        samples: int,
        timestamp: float | None = None,
    ) -> SpectralSnapshot:
        """Push a spectral-scan reading. Becomes the primary source."""
        ts = timestamp if timestamp is not None else time.time()
        snapshot = SpectralSnapshot(
            timestamp=ts,
            floor_dbm=round(floor_dbm, 1),
            median_dbm=round(median_dbm, 1),
            frequency_hz=frequency_hz,
            bandwidth_khz=bandwidth_khz,
            samples=samples,
        )
        self._spectral_last = snapshot
        self._spectral_history.append(snapshot)
        return snapshot

    def reset(self) -> None:
        """Drop all state."""
        self._packet_buffer.clear()
        self._packet_bandwidth_khz = None
        self._packet_last_at = None
        self._spectral_history.clear()
        self._spectral_last = None

    @property
    def rolling_min(self) -> float | None:
        """Lowest packet-derived sample; the fallback estimate."""
        if not self._packet_buffer:
            return None
        return min(s.noise_dbm for s in self._packet_buffer)

    def snapshot(self) -> dict:
        """Serialise current state for the websocket frame.

        Prefers spectral scan when fresh; falls back to packet-derived
        rolling minimum otherwise.
        """
        now = time.time()
        spectral = self._spectral_last
        spectral_fresh = (
            spectral is not None
            and (now - spectral.timestamp) < STALE_AFTER_SECONDS_SPECTRAL
        )

        if spectral_fresh:
            return self._spectral_snapshot(spectral, now)
        return self._packet_snapshot(now, has_stale_spectral=spectral is not None)

    def _spectral_snapshot(
        self, last: SpectralSnapshot, now: float,
    ) -> dict:
        return {
            "value_dbm": last.floor_dbm,
            "median_dbm": last.median_dbm,
            "bandwidth_khz": last.bandwidth_khz,
            "frequency_hz": last.frequency_hz,
            "samples_dbm": [s.floor_dbm for s in self._spectral_history],
            "samples_count": len(self._spectral_history),
            "calibrating": False,
            "last_seen_at": last.timestamp,
            "stale": False,
            "source": SOURCE_SPECTRAL,
            "theoretical_floor_dbm": _theoretical_floor(last.bandwidth_khz),
        }

    def _packet_snapshot(self, now: float, has_stale_spectral: bool) -> dict:
        last_at = self._packet_last_at
        stale = (
            last_at is None
            or (now - last_at) > STALE_AFTER_SECONDS_PACKETS
        )
        floor = self.rolling_min
        return {
            "value_dbm": (round(floor, 1) if floor is not None else None),
            "median_dbm": None,
            "bandwidth_khz": self._packet_bandwidth_khz,
            "frequency_hz": None,
            "samples_dbm": [
                round(s.noise_dbm, 1) for s in self._packet_buffer
            ],
            "samples_count": len(self._packet_buffer),
            "calibrating": len(self._packet_buffer) < CALIBRATING_BELOW,
            "last_seen_at": last_at,
            "stale": stale,
            "source": SOURCE_PACKETS,
            "theoretical_floor_dbm": _theoretical_floor(
                self._packet_bandwidth_khz
            ),
        }


def _theoretical_floor(bandwidth_khz: float | None) -> float | None:
    """Return the kTB+NF noise floor for a bandwidth, or None."""
    if not bandwidth_khz or bandwidth_khz <= 0:
        return None
    bandwidth_hz = bandwidth_khz * 1000.0
    floor = -174.0 + 10.0 * math.log10(bandwidth_hz) + NOISE_FIGURE_DB
    return round(floor, 1)


def _is_physically_plausible(
    sample_dbm: float, bandwidth_khz: float | None
) -> bool:
    """Reject samples that violate physics (below thermal floor)."""
    floor = _theoretical_floor(bandwidth_khz)
    if floor is None:
        return -150.0 <= sample_dbm <= 0.0
    return (floor - 3.0) <= sample_dbm <= 0.0
