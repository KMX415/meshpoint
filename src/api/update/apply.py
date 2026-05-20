"""Run the multi-step update from the dashboard.

The applier walks ``git fetch`` -> ``git checkout -B`` (hard reset to
``origin/<branch>``) -> optional in-process radio release -> ``bash
scripts/install.sh`` -> detached ``systemctl restart meshpoint``.

Radio release stops capture (SX1302 + MeshCore USB) without stopping
the API process, so the NDJSON apply stream can finish. A full
``systemctl stop`` mid-chain would kill Uvicorn and break the dashboard
progress UI. Each step
is its own subprocess invocation so the dashboard can stream a
running log to the operator and so a step that exits non-zero stops
the chain immediately with the failing step labelled.

Subprocess invocation is delegated to a ``Runner`` callable so tests
inject a fake without needing real git or sudo. In production the
default ``ShellRunner`` shells out via ``subprocess.run`` with
``shell=False`` (each command is already a list of args) and the
working directory pinned to ``/opt/meshpoint``.

The applier captures a pre-update commit SHA before mutating the
working tree so the watchdog can roll back by ``git reset --hard``
if the new build fails to come up healthy.
"""

from __future__ import annotations

import logging
import shlex
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable, Optional

from src.api.dangerous.handlers import schedule_systemctl_restart

logger = logging.getLogger(__name__)


@dataclass
class ApplyAttempt:
    """One step in the apply chain."""

    label: str
    args: list[str]
    cwd: Optional[str] = None
    timeout_seconds: float = 600.0
    detached: bool = False


@dataclass
class ApplyResult:
    """Aggregate result for the whole chain."""

    success: bool
    duration_seconds: float
    pre_update_sha: Optional[str]
    target_branch: str
    failed_step: Optional[str] = None
    log: list[dict] = field(default_factory=list)


# Runner takes the args list and returns ``(returncode, stdout, stderr)``.
Runner = Callable[[list[str], Optional[str], float], tuple[int, str, str]]
StreamCallback = Callable[[str, str], None]


def shell_runner(
    args: list[str], cwd: Optional[str], timeout_seconds: float,
) -> tuple[int, str, str]:
    """Default :data:`Runner` -- shells out via ``subprocess.run``."""
    completed = subprocess.run(  # noqa: S603 -- args is a structured list
        args,
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
        check=False,
    )
    return completed.returncode, completed.stdout, completed.stderr


class UpdateApplier:
    """Orchestrate the dashboard-driven update flow."""

    def __init__(
        self,
        *,
        repo_path: str = "/opt/meshpoint",
        install_script: str = "/opt/meshpoint/scripts/install.sh",
        service_name: str = "meshpoint",
        runner: Runner = shell_runner,
        pre_install_hook: Optional[Callable[[], None]] = None,
    ) -> None:
        self._repo_path = repo_path
        self._install_script = install_script
        self._service_name = service_name
        self._runner = runner
        self._pre_install_hook = pre_install_hook

    def set_pre_install_hook(self, hook: Optional[Callable[[], None]]) -> None:
        """Register a callback to release the radio before ``install.sh``."""
        self._pre_install_hook = hook

    def apply(
        self,
        *,
        branch: str,
        on_step: Optional[StreamCallback] = None,
    ) -> ApplyResult:
        """Run the chain end-to-end; return an :class:`ApplyResult`."""
        start = time.time()
        log: list[dict] = []
        pre_sha = self._capture_head_sha()
        steps = self._build_chain(branch)
        for step in steps:
            if step.label == "install.sh" and self._pre_install_hook:
                entry = self._run_pre_install_release(on_step)
                log.append(entry)
                if entry["returncode"] != 0:
                    return ApplyResult(
                        success=False,
                        duration_seconds=time.time() - start,
                        pre_update_sha=pre_sha,
                        target_branch=branch,
                        failed_step=entry["step"],
                        log=log,
                    )
            entry = self._run_step(step, on_step)
            log.append(entry)
            if entry["returncode"] != 0:
                return ApplyResult(
                    success=False,
                    duration_seconds=time.time() - start,
                    pre_update_sha=pre_sha,
                    target_branch=branch,
                    failed_step=step.label,
                    log=log,
                )
        return ApplyResult(
            success=True,
            duration_seconds=time.time() - start,
            pre_update_sha=pre_sha,
            target_branch=branch,
            log=log,
        )

    def rollback(
        self,
        *,
        sha: str,
        on_step: Optional[StreamCallback] = None,
    ) -> ApplyResult:
        """Reset the install tree to a prior commit and restart service."""
        start = time.time()
        log: list[dict] = []
        steps = [
            ApplyAttempt(
                label="git reset",
                args=["sudo", "git", "reset", "--hard", sha],
                cwd=self._repo_path,
            ),
            ApplyAttempt(
                label="restart service",
                args=["sudo", "systemctl", "restart", self._service_name],
                detached=True,
            ),
        ]
        for step in steps:
            entry = self._run_step(step, on_step)
            log.append(entry)
            if entry["returncode"] != 0:
                return ApplyResult(
                    success=False,
                    duration_seconds=time.time() - start,
                    pre_update_sha=sha,
                    target_branch="rollback",
                    failed_step=step.label,
                    log=log,
                )
        return ApplyResult(
            success=True,
            duration_seconds=time.time() - start,
            pre_update_sha=sha,
            target_branch="rollback",
            log=log,
        )

    def _build_chain(self, branch: str) -> Iterable[ApplyAttempt]:
        return (
            ApplyAttempt(
                label="git fetch",
                args=["sudo", "git", "fetch", "origin", branch],
                cwd=self._repo_path,
                timeout_seconds=180,
            ),
            ApplyAttempt(
                label="git checkout",
                args=["sudo", "git", "checkout", "-f", branch],
                cwd=self._repo_path,
                timeout_seconds=60,
            ),
            ApplyAttempt(
                label="git reset",
                args=["sudo", "git", "reset", "--hard", f"origin/{branch}"],
                cwd=self._repo_path,
                timeout_seconds=60,
            ),
            ApplyAttempt(
                label="install.sh",
                args=["sudo", "bash", self._install_script],
                cwd=self._repo_path,
                timeout_seconds=900,
            ),
            ApplyAttempt(
                label="restart service",
                args=["sudo", "systemctl", "restart", self._service_name],
                timeout_seconds=60,
                detached=True,
            ),
        )

    def _run_pre_install_release(
        self, on_step: Optional[StreamCallback],
    ) -> dict:
        label = "release radio"
        if on_step:
            on_step(label, "started")
        try:
            self._pre_install_hook()
            rc = 0
            stderr = ""
        except Exception as exc:
            logger.exception("pre-install radio release failed")
            rc = 1
            stderr = str(exc)
        if on_step:
            on_step(label, "completed" if rc == 0 else "error")
        return {
            "step": label,
            "command": "(in-process capture stop)",
            "returncode": rc,
            "stdout": "",
            "stderr": stderr,
        }

    def _run_step(
        self, step: ApplyAttempt, on_step: Optional[StreamCallback],
    ) -> dict:
        if on_step:
            on_step(step.label, "started")
        if step.detached:
            proc = schedule_systemctl_restart(self._service_name)
            if on_step:
                on_step(step.label, "completed")
            return {
                "step": step.label,
                "command": shlex.join(step.args),
                "returncode": 0,
                "stdout": "",
                "stderr": "",
                "detached": True,
                "pid": proc.pid,
            }
        try:
            rc, stdout, stderr = self._runner(
                step.args, step.cwd, step.timeout_seconds,
            )
        except subprocess.TimeoutExpired:
            if on_step:
                on_step(step.label, "error")
            return {
                "step": step.label,
                "command": shlex.join(step.args),
                "returncode": -1,
                "stdout": "",
                "stderr": "timeout",
            }
        if on_step:
            on_step(step.label, "completed" if rc == 0 else "error")
        return {
            "step": step.label,
            "command": shlex.join(step.args),
            "returncode": rc,
            "stdout": stdout,
            "stderr": stderr,
        }

    def _capture_head_sha(self) -> Optional[str]:
        if not Path(self._repo_path).exists():
            return None
        try:
            rc, stdout, _ = self._runner(
                ["git", "rev-parse", "HEAD"], self._repo_path, 30,
            )
            if rc == 0 and stdout:
                return stdout.strip()
        except Exception:
            logger.debug("failed to capture pre-update SHA", exc_info=True)
        return None
