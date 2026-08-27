"""Recover Meshtastic USB serial after a live link drop.

``writeConfig("lora")`` reboots ESP32 / Xiao boards. meshtastic-python then
emits ``meshtastic.connection.lost`` but leaves the old SerialInterface
object in place, so ``SerialCaptureSource.connected`` stayed true and the
reconnect loop (which only arms when the first open fails) never ran.

This controller closes that handle and schedules the existing backoff
reconnect. The meshtastic publishing thread is not the asyncio loop, so
task creation goes through ``call_soon_threadsafe``. No DTR pulse: that
stormed MeshCore health-check reconnects.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional, Protocol

logger = logging.getLogger(__name__)

_RECONNECT_INITIAL_DELAY_S = 5.0
_RECONNECT_MAX_DELAY_S = 60.0


class SerialReconnectHost(Protocol):
    """Capture source surface the reconnect loop needs."""

    name: str
    _running: bool
    _port: Optional[str]
    _interface: Any

    @property
    def connected(self) -> bool: ...

    def _close_interface(self) -> None: ...

    def _open_interface(self) -> None: ...


class SerialReconnectController:
    """Drop a dead serial handle and retry open with backoff."""

    def __init__(self, host: SerialReconnectHost) -> None:
        self._host = host
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._task: Optional[asyncio.Task] = None

    @property
    def task(self) -> Optional[asyncio.Task]:
        return self._task

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def clear_task(self) -> None:
        self._task = None

    def handle_drop(self, reason: str, interface: Any = None) -> None:
        """Close our interface if this event belongs to us, then reconnect."""
        host = self._host
        if not host._running:
            return
        current = host._interface
        if (
            interface is not None
            and current is not None
            and interface is not current
        ):
            return
        if current is None:
            self.schedule()
            return
        host._close_interface()
        logger.warning(
            "%s: serial link dropped (%s); reconnecting",
            host.name,
            reason,
        )
        self.schedule()

    def schedule(self) -> None:
        if self._task is not None and not self._task.done():
            return
        loop = self._loop
        if loop is None or not loop.is_running():
            logger.warning(
                "%s: cannot schedule serial reconnect (no running event loop)",
                self._host.name,
            )
            return

        def _arm() -> None:
            if self._task is not None and not self._task.done():
                return
            self._task = loop.create_task(
                self._reconnect_until_connected(),
                name=f"{self._host.name}-reconnect",
            )

        try:
            running = asyncio.get_running_loop()
        except RuntimeError:
            running = None
        if running is loop:
            _arm()
        else:
            loop.call_soon_threadsafe(_arm)

    async def cancel(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        self._task = None

    async def _reconnect_until_connected(self) -> None:
        host = self._host
        delay = _RECONNECT_INITIAL_DELAY_S
        try:
            while host._running and not host.connected:
                await asyncio.sleep(delay)
                if not host._running:
                    return
                try:
                    await asyncio.to_thread(host._open_interface)
                    logger.info(
                        "Serial capture recovered on %s",
                        host._port or "auto-detect",
                    )
                    return
                except ImportError:
                    host._running = False
                    raise
                except Exception:
                    next_delay = min(delay * 2, _RECONNECT_MAX_DELAY_S)
                    logger.warning(
                        "Serial reconnect still failing on %s; retry in %.0fs",
                        host._port or "auto-detect",
                        next_delay,
                        exc_info=True,
                    )
                    delay = next_delay
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.exception(
                "Serial reconnect loop error on %s", host.name
            )
