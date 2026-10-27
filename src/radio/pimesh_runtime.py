"""PiMesh eligibility and startup selection. No effects on other installations."""

from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path

from src.radio.pimesh_supervisor import PROVISION, READY, STATE, atomic_json, read_json


def provisioned(config, provision=PROVISION):
    board = getattr(config.device, "radio_hat", "")
    if config.device.platform != "node" or board not in ("pimesh-v1", "pimesh-v2"):
        return False
    try:
        record = read_json(provision)
        return record.get("schema") == 1 and record.get("board") == board
    except (ValueError, OSError):
        return False


def configure_runtime(config, provision=PROVISION, state_path=STATE):
    if not provisioned(config, provision):
        return
    state = read_json(state_path)
    protocol = state.get("active", "meshtastic")
    if protocol not in ("meshtastic", "meshcore"):
        raise ValueError("Invalid PiMesh active protocol")
    config.device.radio_protocol = protocol
    config.capture.sources = (
        ["meshtasticd"] if protocol == "meshtastic" else ["meshcore_usb"]
    )
    config.capture.meshcore_usb.auto_detect = False
    config.capture.meshcore_usb.connection_type = "tcp"
    config.capture.meshcore_usb.tcp_host = "127.0.0.1"
    config.capture.meshcore_usb.tcp_port = 5000
    config.capture.meshtasticd.host = "127.0.0.1"
    config.capture.meshtasticd.port = 4403
    config.capture.meshtasticd.preset = (
        "lora-" + config.device.radio_hat.replace("pimesh-", "pimesh-1w-") + ".yaml"
    )


async def publish_readiness(config, coordinator, ready_path=READY):
    """Publish real protocol handshake state tied to this process's boot operation."""
    if not provisioned(config):
        return
    operation_id = read_json(STATE).get("operation_id")
    while True:
        ready = False
        for source in coordinator.capture_coordinator._sources:
            if (
                config.device.radio_protocol == "meshcore"
                and source.name == "meshcore_usb"
            ):
                ready = bool(source.connected and source.last_device_info)
            elif (
                config.device.radio_protocol == "meshtastic"
                and source.name == "meshtasticd"
                and source.is_running
            ):
                ok, result = await asyncio.to_thread(source.request_read_radio_state)
                ready = bool(
                    ok and isinstance(result, dict) and result.get("local_node_id_hex")
                )
        try:
            atomic_json(
                Path(ready_path),
                {
                    "operation_id": operation_id,
                    "protocol": config.device.radio_protocol,
                    "ready": ready,
                    "updated_at": time.time(),
                },
            )
        except OSError:
            logging.getLogger(__name__).exception("Could not publish radio health")
        await asyncio.sleep(5)
