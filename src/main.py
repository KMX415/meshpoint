"""Meshtastic Concentrator Gateway -- Edge Device Entry Point."""

from __future__ import annotations

import asyncio
import logging

from src.config import load_config, validate_activation
from src.coordinator import PipelineCoordinator

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("concentrator")


def build_pipeline(config_path: str | None = None) -> PipelineCoordinator:
    """Build the full pipeline with configured capture sources."""
    config = load_config(config_path)
    validate_activation(config)
    coordinator = PipelineCoordinator(config)

    for source_name in config.capture.sources:
        if source_name == "serial":
            _add_serial_source(coordinator, config)
        elif source_name == "concentrator":
            _add_concentrator_source(coordinator, config)

    return coordinator


def _add_serial_source(coordinator: PipelineCoordinator, config) -> None:
    try:
        from src.capture.serial_source import SerialCaptureSource
        coordinator.capture_coordinator.add_source(
            SerialCaptureSource(
                port=config.capture.serial_port,
                baud=config.capture.serial_baud,
            )
        )
    except ImportError:
        logger.warning(
            "Serial capture unavailable -- meshtastic package not installed"
        )


def _add_concentrator_source(coordinator: PipelineCoordinator, config) -> None:
    try:
        from src.capture.concentrator_source import ConcentratorCaptureSource
        coordinator.capture_coordinator.add_source(
            ConcentratorCaptureSource(
                spi_path=config.capture.concentrator_spi_device,
                syncword=config.radio.sync_word,
            )
        )
    except Exception:
        logger.exception("Concentrator source unavailable")


async def run_standalone() -> None:
    """Run the pipeline without the web dashboard (CLI mode)."""
    coordinator = build_pipeline()

    def log_packet(packet):
        logger.info(
            "PKT [%s] %s -> %s | type=%s | rssi=%.1f",
            packet.protocol.value,
            packet.source_id,
            packet.destination_id,
            packet.packet_type.value,
            packet.signal.rssi if packet.signal else 0,
        )

    coordinator.on_packet(log_packet)
    await coordinator.start()

    try:
        while True:
            await asyncio.sleep(1)
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass
    finally:
        await coordinator.stop()


if __name__ == "__main__":
    asyncio.run(run_standalone())
