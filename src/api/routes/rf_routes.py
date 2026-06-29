"""RF Environment dashboard — noise floor + spectral scan exposure."""
from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter

from src.api.telemetry.noise_floor import NoiseFloorTracker
from src.config import AppConfig

if TYPE_CHECKING:
    from src.api.telemetry.spectral_scan_service import SpectralScanService

router = APIRouter(prefix="/api/rf", tags=["rf"])

# Shown when interval > 0 but the SX1261 is not on a Pi-visible SPI bus
# (RAK2287, RAK5146, SenseCap M1, and most fleet carriers).
_FLEET_SPECTRAL_SCAN_NOTE = (
    "Expected on RAK V2 and SenseCap M1; packet fallback is normal."
)

_tracker: NoiseFloorTracker | None = None
_scan_service: SpectralScanService | None = None
_config: AppConfig | None = None


def init_routes(
    tracker: NoiseFloorTracker,
    scan_service: SpectralScanService | None,
    config: AppConfig,
) -> None:
    global _tracker, _scan_service, _config
    _tracker = tracker
    _scan_service = scan_service
    _config = config


def _spectral_status() -> dict:
    radio = _config.radio if _config else None
    interval = (
        float(radio.spectral_scan_interval_seconds)
        if radio and radio.spectral_scan_interval_seconds is not None
        else 0.0
    )
    enabled = interval > 0
    frequency_hz = (
        int(radio.frequency_mhz * 1_000_000)
        if radio and radio.frequency_mhz is not None
        else None
    )
    bandwidth_khz = radio.bandwidth_khz if radio else None

    if not enabled:
        return {
            "enabled": False,
            "supported": False,
            "running": False,
            "interval_seconds": interval,
            "frequency_hz": frequency_hz,
            "bandwidth_khz": bandwidth_khz,
            "scans_run": 0,
            "scans_failed": 0,
            "histogram": None,
            "message": (
                "Hardware spectral scan disabled "
                "(radio.spectral_scan_interval_seconds is 0)."
            ),
        }

    if _scan_service is None:
        return {
            "enabled": True,
            "supported": False,
            "running": False,
            "interval_seconds": interval,
            "frequency_hz": frequency_hz,
            "bandwidth_khz": bandwidth_khz,
            "scans_run": 0,
            "scans_failed": 0,
            "histogram": None,
            "fleet_expected_fallback": True,
            "message": (
                "Spectral scan not available on this hardware or HAL build. "
                "Noise floor uses packet-derived fallback. "
                f"{_FLEET_SPECTRAL_SCAN_NOTE}"
            ),
        }

    return {
        "enabled": True,
        "supported": _scan_service.hardware_supported,
        "running": _scan_service.is_running,
        "interval_seconds": interval,
        "frequency_hz": frequency_hz,
        "bandwidth_khz": bandwidth_khz,
        "scans_run": _scan_service.scans_run,
        "scans_failed": _scan_service.scans_failed,
        "histogram": _scan_service.histogram_payload(),
        "message": None,
    }


@router.get("/status")
async def rf_status() -> dict:
    """Noise-floor state and latest spectral-scan histogram for the RF tab."""
    noise_floor = _tracker.snapshot() if _tracker else {}
    return {
        "noise_floor": noise_floor,
        "spectral_scan": _spectral_status(),
    }
