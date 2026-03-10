from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class WebSocketManager:
    """Manages connected dashboard WebSocket clients and broadcasts updates."""

    def __init__(self):
        self._connections: list[WebSocket] = []
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self._connections.append(websocket)
        logger.info(
            "WebSocket client connected (%d total)", len(self._connections)
        )

    async def disconnect(self, websocket: WebSocket) -> None:
        async with self._lock:
            if websocket in self._connections:
                self._connections.remove(websocket)
        logger.info(
            "WebSocket client disconnected (%d remaining)",
            len(self._connections),
        )

    async def broadcast(self, event_type: str, data: Any) -> None:
        """Send a JSON message to all connected clients."""
        if not self._connections:
            return

        message = json.dumps({"type": event_type, "data": data})
        disconnected: list[WebSocket] = []

        async with self._lock:
            for ws in self._connections:
                try:
                    await ws.send_text(message)
                except Exception:
                    disconnected.append(ws)

            for ws in disconnected:
                self._connections.remove(ws)

    @property
    def client_count(self) -> int:
        return len(self._connections)
