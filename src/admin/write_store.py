"""In-memory state for remote config write + verify operations."""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Literal

WriteStatus = Literal[
    "idle",
    "writing",
    "verifying",
    "verified",
    "verify_timeout",
    "failed",
]

WRITE_DEBOUNCE_SECONDS = 30.0


@dataclass
class WriteOperationState:
    node_id: str
    operation_id: str = ""
    status: WriteStatus = "idle"
    changes: dict[str, Any] = field(default_factory=dict)
    packets_sent: list[str] = field(default_factory=list)
    verify_sections: list[str] = field(default_factory=list)
    verify_result: dict[str, Any] | None = None
    error: str = ""
    started_at: float = 0.0
    completed_at: float = 0.0


class WriteOperationStore:
    def __init__(self) -> None:
        self._by_node: dict[str, WriteOperationState] = {}

    def get(self, node_id: str) -> WriteOperationState | None:
        return self._by_node.get(node_id)

    def can_write(self, node_id: str) -> tuple[bool, str]:
        state = self._by_node.get(node_id)
        if state is None:
            return True, ""
        if state.status in ("writing", "verifying"):
            return False, "Write or verify already in progress"
        if state.started_at and time.time() - state.started_at < WRITE_DEBOUNCE_SECONDS:
            remaining = int(WRITE_DEBOUNCE_SECONDS - (time.time() - state.started_at))
            return False, f"Wait {remaining}s before another write"
        return True, ""

    def begin(
        self,
        node_id: str,
        *,
        changes: dict[str, Any],
        verify_sections: list[str],
    ) -> WriteOperationState:
        state = WriteOperationState(
            node_id=node_id,
            operation_id=uuid.uuid4().hex[:12],
            status="writing",
            changes=changes,
            verify_sections=list(verify_sections),
            started_at=time.time(),
        )
        self._by_node[node_id] = state
        return state

    def mark_verifying(self, node_id: str, packets_sent: list[str]) -> None:
        state = self._by_node.get(node_id)
        if state is None:
            return
        state.packets_sent = list(packets_sent)
        state.status = "verifying"

    def complete_verified(
        self,
        node_id: str,
        verify_result: dict[str, Any],
    ) -> None:
        state = self._by_node.get(node_id)
        if state is None:
            return
        state.status = "verified"
        state.verify_result = verify_result
        state.completed_at = time.time()

    def fail(self, node_id: str, error: str) -> None:
        state = self._by_node.get(node_id)
        if state is None:
            return
        state.status = "failed"
        state.error = error
        state.completed_at = time.time()

    def verify_timeout(self, node_id: str) -> None:
        state = self._by_node.get(node_id)
        if state is None:
            return
        state.status = "verify_timeout"
        state.error = "Verify read timed out after write"
        state.completed_at = time.time()
