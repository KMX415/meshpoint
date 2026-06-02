"""Concrete handler factories for dangerous actions.

Each ``build_*`` function returns a :class:`DangerousAction` whose
handler closes over the live dependencies passed in. This keeps the
production wiring in ``server.py`` declarative -- it asks for an
action by name, gets a closure with the right collaborators
already bound, and registers it.

Synchronous handler bodies dispatch async work (subprocess starts,
node-repo writes) via ``asyncio.run_coroutine_threadsafe`` against
a passed-in loop reference. That way the registry can stay sync
even when the work is async.
"""

from __future__ import annotations

import logging
import shlex
import subprocess
from typing import Awaitable, Callable, Optional

from src.api.dangerous.actions import DangerousAction, DangerousActionResult

logger = logging.getLogger(__name__)


Runner = Callable[[list[str], Optional[float]], tuple[int, str, str]]
AsyncDispatch = Callable[[Awaitable], object]

_SYSTEMCTL = "/usr/bin/systemctl"


def schedule_systemctl_restart(service_name: str) -> subprocess.Popen:
    """Start a detached restart so this process is not killed mid-wait."""
    return subprocess.Popen(  # noqa: S603 -- structured argv
        ["sudo", _SYSTEMCTL, "restart", service_name],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        start_new_session=True,
    )


def schedule_detached_apply_finish(
    finish_script: str = "/opt/meshpoint/scripts/apply_finish.sh",
) -> subprocess.Popen:
    """Stop service, refresh venv deps, post_update, restart -- outlives this process."""
    return subprocess.Popen(  # noqa: S603 -- structured argv
        ["sudo", "/bin/bash", finish_script],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        start_new_session=True,
    )


def shell_runner(
    args: list[str], timeout_seconds: Optional[float] = 60.0,
) -> tuple[int, str, str]:
    completed = subprocess.run(  # noqa: S603 -- args is a structured list
        args,
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
        check=False,
    )
    return completed.returncode, completed.stdout, completed.stderr


def build_restart_service_action(
    *,
    service_name: str = "meshpoint",
    runner: Runner = shell_runner,
    detached: bool = True,
) -> DangerousAction:
    def handler() -> DangerousActionResult:
        cmd = ["sudo", _SYSTEMCTL, "restart", service_name]
        if detached:
            proc = schedule_systemctl_restart(service_name)
            return DangerousActionResult(
                success=True,
                message="service restart initiated",
                details={
                    "command": shlex.join(cmd),
                    "detached": True,
                    "pid": proc.pid,
                },
            )
        rc, stdout, stderr = runner(cmd, 60.0)
        return DangerousActionResult(
            success=rc == 0,
            message="service restarted" if rc == 0 else "restart failed",
            details={
                "command": shlex.join(cmd),
                "returncode": rc,
                "stdout": stdout,
                "stderr": stderr,
            },
        )
    return DangerousAction(
        id="restart_service",
        label="Restart service",
        description="Briefly stops packet capture while systemd restarts the meshpoint unit.",
        confirmation_text="restart",
        handler=handler,
    )


def build_restart_concentrator_action(
    *,
    dispatch: AsyncDispatch,
    restart_coro_factory: Callable[[], Awaitable[bool]],
) -> DangerousAction:
    """Reload the SX1302 HAL in-process (no systemd unit restart)."""

    def handler() -> DangerousActionResult:
        try:
            future = dispatch(restart_coro_factory())
            ok = future.result(timeout=60) if hasattr(future, "result") else future
            return DangerousActionResult(
                success=bool(ok),
                message=(
                    "concentrator restarted"
                    if ok
                    else "concentrator restart unavailable"
                ),
            )
        except Exception as exc:
            logger.exception("restart_concentrator handler failed")
            return DangerousActionResult(
                success=False,
                message=f"concentrator restart failed: {exc}",
            )

    return DangerousAction(
        id="restart_concentrator",
        label="Restart concentrator",
        description="Reloads the SX1302 capture pipeline. Use when packets stop flowing.",
        confirmation_text="restart",
        handler=handler,
    )


def build_clear_database_action(
    *,
    dispatch: AsyncDispatch,
    clear_coro_factory: Callable[[], Awaitable[int]],
) -> DangerousAction:
    """Drop every row from the packets/messages/nodes tables."""

    def handler() -> DangerousActionResult:
        try:
            future = dispatch(clear_coro_factory())
            removed = future.result(timeout=30) if hasattr(future, "result") else future
            return DangerousActionResult(
                success=True,
                message=f"database cleared ({removed} rows removed)",
                details={"removed": int(removed)},
            )
        except Exception as exc:
            logger.exception("clear_database handler failed")
            return DangerousActionResult(
                success=False, message=f"clear failed: {exc}",
            )
    return DangerousAction(
        id="clear_database",
        label="Clear database",
        description="Drops every captured packet, message, and node row. Cannot be undone.",
        confirmation_text="clear database",
        handler=handler,
    )


def build_wipe_phantoms_action(
    *,
    dispatch: AsyncDispatch,
    wipe_coro_factory: Callable[[], Awaitable[int]],
) -> DangerousAction:
    """Remove nodes that never sent a valid CRC packet (phantoms)."""

    def handler() -> DangerousActionResult:
        try:
            future = dispatch(wipe_coro_factory())
            removed = future.result(timeout=30) if hasattr(future, "result") else future
            return DangerousActionResult(
                success=True,
                message=f"removed {int(removed)} phantom node(s)",
                details={"removed": int(removed)},
            )
        except Exception as exc:
            logger.exception("wipe_phantoms handler failed")
            return DangerousActionResult(
                success=False, message=f"wipe failed: {exc}",
            )
    return DangerousAction(
        id="wipe_phantom_nodes",
        label="Wipe phantom nodes",
        description="Removes nodes recorded without a valid CRC. Useful after a bad RX session.",
        confirmation_text="wipe phantoms",
        handler=handler,
    )


def build_force_nodeinfo_action(
    *,
    dispatch: AsyncDispatch,
    broadcast_coro_factory: Callable[[], Awaitable[bool]],
) -> DangerousAction:
    """Force an immediate NodeInfo broadcast outside the schedule."""

    def handler() -> DangerousActionResult:
        try:
            future = dispatch(broadcast_coro_factory())
            ok = future.result(timeout=30) if hasattr(future, "result") else future
            return DangerousActionResult(
                success=bool(ok),
                message="nodeinfo broadcast queued" if ok else "broadcast unavailable",
            )
        except Exception as exc:
            logger.exception("force_nodeinfo handler failed")
            return DangerousActionResult(
                success=False, message=f"broadcast failed: {exc}",
            )
    return DangerousAction(
        id="force_nodeinfo",
        label="Force NodeInfo broadcast",
        description="Queues an immediate NodeInfo packet for adjacent nodes.",
        confirmation_text="broadcast",
        handler=handler,
    )
