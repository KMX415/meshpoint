"""In-memory pending remote config read requests (one slot per node)."""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Literal

RequestStatus = Literal["idle", "pending", "complete", "timeout", "error"]

REQUEST_TIMEOUT_SECONDS = 30.0
DEBOUNCE_SECONDS = 30.0


@dataclass
class ConfigReadState:
    node_id: str
    request_id: str = ""
    section: str = "device"
    status: RequestStatus = "idle"
    requested_at: float = 0.0
    completed_at: float = 0.0
    packet_id: str = ""
    config: dict[str, Any] | None = None
    error: str = ""
    expected_response: str = "get_config_response"


class PendingConfigStore:
    """Tracks pending/completed config reads keyed by normalized node ID."""

    def __init__(self) -> None:
        self._by_node: dict[str, ConfigReadState] = {}

    def get(self, node_id: str) -> ConfigReadState | None:
        state = self._by_node.get(node_id)
        if state is None:
            return None
        self._maybe_timeout(state)
        return state

    def can_request(self, node_id: str) -> tuple[bool, str]:
        state = self._by_node.get(node_id)
        if state is None:
            return True, ""
        self._maybe_timeout(state)
        if state.status == "pending":
            elapsed = time.time() - state.requested_at
            if elapsed < DEBOUNCE_SECONDS:
                remaining = int(DEBOUNCE_SECONDS - elapsed)
                return False, f"Request in progress; retry in {remaining}s"
        if state.status in ("pending", "complete", "timeout", "error"):
            elapsed = time.time() - state.requested_at
            if elapsed < DEBOUNCE_SECONDS:
                remaining = int(DEBOUNCE_SECONDS - elapsed)
                return False, f"Wait {remaining}s before another request"
        return True, ""

    def begin(
        self,
        node_id: str,
        *,
        section: str,
        packet_id: str,
        expected_response: str,
    ) -> ConfigReadState:
        state = ConfigReadState(
            node_id=node_id,
            request_id=uuid.uuid4().hex[:12],
            section=section,
            status="pending",
            requested_at=time.time(),
            packet_id=packet_id,
            expected_response=expected_response,
            config=None,
            error="",
        )
        self._by_node[node_id] = state
        return state

    def complete(
        self,
        node_id: str,
        config: dict[str, Any],
    ) -> None:
        state = self._by_node.get(node_id)
        if state is None or state.status != "pending":
            return
        state.status = "complete"
        state.completed_at = time.time()
        state.config = config

    def fail(self, node_id: str, error: str) -> None:
        state = self._by_node.get(node_id)
        if state is None:
            return
        state.status = "error"
        state.completed_at = time.time()
        state.error = error

    def _maybe_timeout(self, state: ConfigReadState) -> None:
        if state.status != "pending":
            return
        if time.time() - state.requested_at >= REQUEST_TIMEOUT_SECONDS:
            state.status = "timeout"
            state.completed_at = time.time()
            state.error = "No response within 30 seconds"
