"""Authenticated WebSocket subscribers for live firmware flash logs."""
from __future__ import annotations

import asyncio
import logging

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class FlashLogBroadcaster:
    def __init__(self) -> None:
        self._subscribers: set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def subscribe(self, websocket: WebSocket) -> None:
        async with self._lock:
            self._subscribers.add(websocket)

    async def unsubscribe(self, websocket: WebSocket) -> None:
        async with self._lock:
            self._subscribers.discard(websocket)

    async def broadcast(self, message: str) -> None:
        async with self._lock:
            dead: set[WebSocket] = set()
            for ws in self._subscribers:
                try:
                    await ws.send_text(message)
                except Exception:
                    dead.add(ws)
            self._subscribers.difference_update(dead)
