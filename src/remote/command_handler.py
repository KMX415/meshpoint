"""Dispatches remote commands received from the cloud via WebSocket."""

from __future__ import annotations

import logging
from typing import Any, Callable

logger = logging.getLogger(__name__)

DANGEROUS_ACTIONS = frozenset({"restart_service", "apply_update"})


class CommandHandler:
    """Routes incoming command messages to the appropriate executor."""

    def __init__(self) -> None:
        self._executors: dict[str, Callable[..., dict[str, Any]]] = {}

    def register(self, action: str, executor: Callable[..., dict[str, Any]]) -> None:
        self._executors[action] = executor

    async def handle(self, message: dict[str, Any]) -> dict[str, Any]:
        command_id = message.get("command_id", "")
        action = message.get("action", "")
        params = message.get("params") or {}
        confirm = message.get("confirm", False)

        if not action:
            return self._error_response(command_id, "Missing action")

        if action not in self._executors:
            return self._error_response(command_id, f"Unknown action: {action}")

        if action in DANGEROUS_ACTIONS and not confirm:
            return self._confirm_required(command_id, action)

        logger.info("Executing command: action=%s id=%s", action, command_id)

        try:
            executor = self._executors[action]
            result = await executor(params) if _is_coroutine(executor) else executor(params)
            return {
                "type": "command_response",
                "command_id": command_id,
                "status": "success",
                "data": result,
            }
        except Exception as exc:
            logger.exception("Command failed: action=%s id=%s", action, command_id)
            return self._error_response(command_id, str(exc))

    @staticmethod
    def _error_response(command_id: str, error: str) -> dict[str, Any]:
        return {
            "type": "command_response",
            "command_id": command_id,
            "status": "error",
            "data": {"error": error},
        }

    @staticmethod
    def _confirm_required(command_id: str, action: str) -> dict[str, Any]:
        return {
            "type": "command_response",
            "command_id": command_id,
            "status": "confirm_required",
            "data": {
                "message": f"Action '{action}' requires confirm: true",
            },
        }


def _is_coroutine(func: Callable) -> bool:
    import asyncio
    return asyncio.iscoroutinefunction(func)
