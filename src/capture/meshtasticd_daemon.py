"""Coordinate with the local meshtasticd systemd service."""

from __future__ import annotations

import logging
import socket
import subprocess
import time

logger = logging.getLogger(__name__)

_SERVICE_NAME = "meshtasticd"
_WAIT_PORT_SECONDS = 30.0
_POLL_INTERVAL = 0.5


def is_service_active() -> bool:
    try:
        result = subprocess.run(
            ["sudo", "/usr/bin/systemctl", "is-active", _SERVICE_NAME],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        return result.stdout.strip() == "active"
    except Exception:
        return False


def wait_for_tcp_port(host: str = "127.0.0.1", port: int = 4403) -> None:
    """Wait until meshtasticd's TCP API port accepts connections."""
    _wait_for_tcp_port(host, port)


def restart_service_and_wait(host: str = "127.0.0.1", port: int = 4403) -> None:
    """Restart meshtasticd and wait until its TCP API port accepts connections."""
    if not is_service_active():
        logger.debug("%s not active; skipping restart", _SERVICE_NAME)
        return

    logger.info("Restarting %s to reset the TCP phone client", _SERVICE_NAME)
    result = subprocess.run(
        ["sudo", "/usr/bin/systemctl", "restart", _SERVICE_NAME],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    if result.returncode != 0:
        logger.warning(
            "meshtasticd restart failed (rc=%s): %s",
            result.returncode,
            (result.stderr or result.stdout or "").strip(),
        )
        raise RuntimeError("meshtasticd restart failed")
    _wait_for_tcp_port(host, port)


def _wait_for_tcp_port(host: str, port: int) -> None:
    deadline = time.monotonic() + _WAIT_PORT_SECONDS
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((host, port), timeout=1.0):
                logger.info(
                    "meshtasticd TCP port %d is accepting connections", port
                )
                return
        except OSError:
            time.sleep(_POLL_INTERVAL)
    raise TimeoutError(
        f"meshtasticd port {port} not ready after {_WAIT_PORT_SECONDS:.0f}s"
    )
