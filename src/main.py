"""Meshtastic Concentrator Gateway -- Edge Device Entry Point."""

from __future__ import annotations

import asyncio
import logging

from src.config import load_config, validate_activation
from src.coordinator import PipelineCoordinator
from src.log_format import print_banner, print_packet, setup_logging

setup_logging()
logger = logging.getLogger("concentrator")


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
        from src.hal.concentrator_config import ConcentratorChannelPlan
        channel_plan = ConcentratorChannelPlan.for_config(
            config.radio.region, config.radio.protocol,
        )
        coordinator.capture_coordinator.add_source(
            ConcentratorCaptureSource(
                spi_path=config.capture.concentrator_spi_device,
                syncword=config.radio.sync_word,
                channel_plan=channel_plan,
            )
        )
    except Exception:
        logger.exception("Concentrator source unavailable")


async def run_standalone() -> None:
    """Run the pipeline without the web dashboard (CLI mode)."""
    config = load_config()
    validate_activation(config)
    coordinator = PipelineCoordinator(config)

    for source_name in config.capture.sources:
        if source_name == "serial":
            _add_serial_source(coordinator, config)
        elif source_name == "concentrator":
            _add_concentrator_source(coordinator, config)

    coordinator.on_packet(lambda pkt: print_packet(pkt))
    await coordinator.start()
    print_banner(config)
    logger.info("Standalone mode -- listening for packets")

    try:
        while True:
            await asyncio.sleep(1)
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass
    finally:
        await coordinator.stop()


if __name__ == "__main__":
    asyncio.run(run_standalone())
