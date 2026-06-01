"""NDJSON streaming helpers for dashboard-driven updates.

Each line is one JSON object so the browser can parse progress with a
simple ``fetch`` + ``ReadableStream`` reader (no WebSocket required).
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import asdict
from typing import AsyncIterator, Literal

from src.api.update.apply import ApplyResult, UpdateApplier

StreamMode = Literal["apply", "rollback"]


def encode_ndjson_event(payload: dict) -> bytes:
    """Serialize one event as a UTF-8 line."""
    return (json.dumps(payload, separators=(",", ":")) + "\n").encode("utf-8")


async def stream_update(
    applier: UpdateApplier,
    *,
    mode: StreamMode,
    branch: str | None = None,
    sha: str | None = None,
) -> AsyncIterator[bytes]:
    """Yield NDJSON events while ``apply`` or ``rollback`` runs off-thread."""
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue[dict] = asyncio.Queue()
    holder: dict[str, ApplyResult] = {}

    def on_step(step: str, phase: str, detail: dict | None = None) -> None:
        payload: dict = {"type": "step", "step": step, "phase": phase}
        if detail is not None:
            payload["detail"] = detail
        loop.call_soon_threadsafe(queue.put_nowait, payload)

    def run_chain() -> None:
        if mode == "rollback":
            if not sha:
                raise ValueError("sha required for rollback stream")
            holder["result"] = applier.rollback(sha=sha, on_step=on_step)
        else:
            if not branch:
                raise ValueError("branch required for apply stream")
            holder["result"] = applier.apply(branch=branch, on_step=on_step)

    meta = {"type": "started", "mode": mode}
    if mode == "rollback":
        meta["sha"] = sha
    else:
        meta["branch"] = branch
    yield encode_ndjson_event(meta)

    task = loop.run_in_executor(None, run_chain)
    while True:
        drained = task.done() and queue.empty()
        if drained:
            break
        try:
            event = await asyncio.wait_for(queue.get(), timeout=0.15)
        except asyncio.TimeoutError:
            continue
        yield encode_ndjson_event(event)

    await task
    result = holder.get("result")
    if result is None:
        yield encode_ndjson_event({
            "type": "error",
            "message": "update_finished_without_result",
        })
        return
    yield encode_ndjson_event({"type": "result", "result": asdict(result)})
