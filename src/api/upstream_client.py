from __future__ import annotations

import asyncio
import json
import logging
from collections import deque
from datetime import datetime, timezone
from typing import Optional

import websockets
from websockets.exceptions import ConnectionClosed

from src.config import UpstreamConfig
from src.log_format import CYAN, DIM, GREEN, RED, RESET, YELLOW
from src.models.device_identity import DeviceIdentity
from src.models.packet import Packet
from src.remote.command_handler import CommandHandler
from src.remote.executors import (
    execute_apply_update,
    execute_get_logs,
    execute_get_metrics,
    execute_get_status,
    execute_ping,
    execute_restart_service,
)

logger = logging.getLogger(__name__)


class UpstreamClient:
    """WebSocket client that ships decoded data to the central platform.

    Features:
    - Automatic reconnection with exponential backoff
    - Local buffer during disconnects (up to buffer_max_size)
    - Device authentication via token in initial handshake
    - Serialized sends via asyncio.Lock to prevent frame corruption
    """

    HEARTBEAT_INTERVAL_SECONDS = 300  # 5 minutes

    def __init__(
        self,
        config: UpstreamConfig,
        identity: DeviceIdentity,
    ):
        self._config = config
        self._identity = identity
        self._connection: Optional[websockets.WebSocketClientProtocol] = None
        self._buffer: deque[dict] = deque(maxlen=config.buffer_max_size)
        self._running = False
        self._connected = False
        self._task: Optional[asyncio.Task] = None
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._reconnect_delay = config.reconnect_interval_seconds
        self._command_handler = self._build_command_handler()
        self._listener_task: Optional[asyncio.Task] = None
        self._send_lock = asyncio.Lock()

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def buffer_size(self) -> int:
        return len(self._buffer)

    async def start(self) -> None:
        if not self._config.enabled:
            logger.info(
                f" {CYAN}--{RESET} {DIM}UPSTREAM{RESET}  disabled"
            )
            return
        self._running = True
        self._task = asyncio.create_task(
            self._connection_loop(), name="upstream-ws"
        )
        logger.info(
            f" {CYAN}--{RESET} {GREEN}UPSTREAM{RESET}  "
            f"connecting to {self._config.url}"
        )

    async def stop(self) -> None:
        self._running = False
        if self._connection:
            await self._connection.close()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info(
            f" {CYAN}--{RESET} {DIM}UPSTREAM{RESET}  stopped"
        )

    def send_packet(self, packet: Packet) -> None:
        """Queue a packet for upstream delivery."""
        if not self._config.enabled:
            return
        message = {
            "type": "packet",
            "device_id": self._identity.device_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "data": packet.to_dict(),
        }
        self._buffer.append(message)

    async def _connection_loop(self) -> None:
        backoff = self._reconnect_delay

        while self._running:
            try:
                await self._connect_and_run()
                backoff = self._reconnect_delay
            except ConnectionClosed:
                logger.warning(
                    f" {CYAN}--{RESET} {RED}UPSTREAM{RESET}  "
                    f"connection closed"
                )
            except Exception:
                logger.exception(
                    f" {CYAN}--{RESET} {RED}UPSTREAM{RESET}  "
                    f"connection error"
                )

            self._connected = False
            if self._running:
                logger.info(
                    f" {CYAN}--{RESET} {YELLOW}UPSTREAM{RESET}  "
                    f"reconnecting in {backoff:.0f}s "
                    f"{DIM}({len(self._buffer)} buffered){RESET}"
                )
                await asyncio.sleep(backoff)
                backoff = min(backoff * 1.5, 60)

    async def _connect_and_run(self) -> None:
        headers = self._build_auth_headers()
        auth_status = "present" if headers.get("Authorization") else "MISSING"
        logger.info(
            f" {CYAN}--{RESET} {GREEN}UPSTREAM{RESET}  "
            f"connecting  {DIM}auth={auth_status}{RESET}"
        )

        async with websockets.connect(
            self._config.url,
            additional_headers=headers,
            open_timeout=30,
            ping_interval=30,
            ping_timeout=10,
        ) as ws:
            self._connection = ws
            self._connected = True
            logger.info(
                f" {CYAN}--{RESET} {GREEN}UPSTREAM{RESET}  "
                f"connected to {self._config.url}"
            )

            await self._send(self._build_registration())
            self._heartbeat_task = asyncio.create_task(
                self._heartbeat_loop(), name="upstream-heartbeat"
            )
            self._listener_task = asyncio.create_task(
                self._listener_loop(ws), name="upstream-listener"
            )

            try:
                await self._flush_buffer()

                while self._running:
                    if self._buffer:
                        await self._flush_buffer()
                    else:
                        await asyncio.sleep(0.5)
            finally:
                for task in (self._heartbeat_task, self._listener_task):
                    if task:
                        task.cancel()
                        try:
                            await task
                        except asyncio.CancelledError:
                            pass

    async def _heartbeat_loop(self) -> None:
        while self._running and self._connected:
            await asyncio.sleep(self.HEARTBEAT_INTERVAL_SECONDS)
            try:
                heartbeat = {
                    "type": "heartbeat",
                    "device_id": self._identity.device_id,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
                await self._send(heartbeat)
                logger.debug("Heartbeat sent")
            except ConnectionClosed:
                break
            except Exception:
                logger.warning("Failed to send heartbeat", exc_info=True)
                break

    def _build_registration(self) -> dict:
        return {
            "type": "register",
            "device": self._identity.to_dict(),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    async def _flush_buffer(self) -> None:
        while self._buffer and self._connected:
            message = self._buffer[0]
            try:
                await self._send(message)
                self._buffer.popleft()
            except ConnectionClosed:
                self._connected = False
                raise

    async def _send(self, message: dict) -> None:
        if not (self._connection and self._connected):
            return
        async with self._send_lock:
            await self._connection.send(json.dumps(message))

    async def _listener_loop(
        self, ws: websockets.WebSocketClientProtocol
    ) -> None:
        """Read incoming messages from the cloud and dispatch commands."""
        try:
            async for raw in ws:
                try:
                    message = json.loads(raw)
                except json.JSONDecodeError:
                    logger.warning("Non-JSON message from cloud: %s", raw[:120])
                    continue

                if message.get("type") == "command":
                    response = await self._command_handler.handle(message)
                    response["device_id"] = self._identity.device_id
                    try:
                        await self._send(response)
                        logger.info(
                            "Command response sent: cmd=%s status=%s",
                            response.get("command_id"),
                            response.get("status"),
                        )
                    except Exception:
                        logger.exception("Failed to send command response")
                else:
                    logger.debug(
                        "Ignoring cloud message type=%s", message.get("type")
                    )
        except ConnectionClosed:
            logger.debug("Listener loop: connection closed")
        except asyncio.CancelledError:
            pass

    @staticmethod
    def _build_command_handler() -> CommandHandler:
        handler = CommandHandler()
        handler.register("ping", execute_ping)
        handler.register("get_status", execute_get_status)
        handler.register("get_metrics", execute_get_metrics)
        handler.register("get_logs", execute_get_logs)
        handler.register("restart_service", execute_restart_service)
        handler.register("apply_update", execute_apply_update)
        return handler

    def _build_auth_headers(self) -> dict[str, str]:
        headers: dict[str, str] = {
            "X-Device-Id": self._identity.device_id,
        }
        token = self._config.auth_token or self._identity.auth_token
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return headers
