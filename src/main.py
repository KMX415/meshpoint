"""Meshtastic Concentrator Gateway -- Edge Device Entry Point."""

from __future__ import annotations

import asyncio
import logging

from src.capture.source_registry import register_capture_sources
from src.config import load_config, validate_activation
from src.coordinator import PipelineCoordinator
from src.log_format import print_banner, print_packet, setup_logging

setup_logging()
logger = logging.getLogger("concentrator")


async def run_standalone() -> None:
    """Run the pipeline without the web dashboard (CLI mode)."""
    config = load_config()
    validate_activation(config)
    coordinator = PipelineCoordinator(config)
    register_capture_sources(coordinator, config)

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
