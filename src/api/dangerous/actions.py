"""Registry of dangerous-action handlers with structured results.

Each ``DangerousAction`` is a small dataclass + callable. The
registry maps an opaque action id (the same string the frontend
typed-confirmation modal verifies against) to its handler so the
HTTP route layer can stay generic -- it just looks up the action,
invokes it, and returns the structured result.

The action callables are deliberately synchronous so the registry
can be unit-tested without an event loop. Async work (subprocess
launches, database calls) is dispatched inside the callable using
``asyncio.run_coroutine_threadsafe`` when needed.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Callable, Iterable, Optional

logger = logging.getLogger(__name__)


@dataclass
class DangerousActionResult:
    success: bool
    message: str = ""
    details: dict = field(default_factory=dict)


ActionHandler = Callable[[], DangerousActionResult]


@dataclass(frozen=True)
class DangerousAction:
    """One operator-visible dangerous operation."""

    id: str
    label: str
    description: str
    confirmation_text: str
    handler: ActionHandler

    def to_payload(self) -> dict:
        return {
            "id": self.id,
            "label": self.label,
            "description": self.description,
            "confirmation_text": self.confirmation_text,
        }


class DangerousActionRegistry:
    """Lookup helper for the route layer."""

    def __init__(self, actions: Iterable[DangerousAction]) -> None:
        self._actions: tuple[DangerousAction, ...] = tuple(actions)
        self._by_id: dict[str, DangerousAction] = {a.id: a for a in self._actions}

    def actions(self) -> tuple[DangerousAction, ...]:
        return self._actions

    def to_payload(self) -> list[dict]:
        return [a.to_payload() for a in self._actions]

    def find(self, action_id: str) -> Optional[DangerousAction]:
        return self._by_id.get(action_id)

    def invoke(self, action_id: str) -> DangerousActionResult:
        action = self.find(action_id)
        if action is None:
            return DangerousActionResult(
                success=False, message=f"unknown action: {action_id}"
            )
        try:
            return action.handler()
        except Exception as exc:
            logger.exception("dangerous action %s raised", action_id)
            return DangerousActionResult(
                success=False, message=f"handler raised: {exc}",
            )
