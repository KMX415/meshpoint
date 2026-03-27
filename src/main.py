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
        coordinator.capture_coordinator.add_source(
            ConcentratorCaptureSource(
                spi_path=config.capture.concentrator_spi_device,
                syncword=config.radio.sync_word,
                radio_config=config.radio,
            )
        )
    except Exception:
        logger.exception("Concentrator source unavailable")


def _add_meshcore_usb_source(coordinator: PipelineCoordinator, config) -> None:
    try:
        from src.capture.meshcore_usb_source import MeshcoreUsbCaptureSource
        usb_cfg = config.capture.meshcore_usb
        coordinator.capture_coordinator.add_source(
            MeshcoreUsbCaptureSource(
                serial_port=usb_cfg.serial_port,
                baud_rate=usb_cfg.baud_rate,
                auto_detect=usb_cfg.auto_detect,
            )
        )
    except ImportError:
        logger.warning(
            "MeshCore USB unavailable -- meshcore package not installed"
        )


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
        elif source_name == "meshcore_usb":
            _add_meshcore_usb_source(coordinator, config)

    if (
        "meshcore_usb" not in config.capture.sources
        and config.capture.meshcore_usb.auto_detect
    ):
        _add_meshcore_usb_source(coordinator, config)

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
