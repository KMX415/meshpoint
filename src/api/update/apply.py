"""Run the multi-step update from the dashboard.

The applier walks ``git fetch`` -> ``git checkout`` -> ``bash
scripts/install.sh`` -> ``systemctl restart meshpoint``. Each step
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

logger = logging.getLogger(__name__)


@dataclass
class ApplyAttempt:
    """One step in the apply chain."""

    label: str
    args: list[str]
    cwd: Optional[str] = None
    timeout_seconds: float = 600.0


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
    ) -> None:
        self._repo_path = repo_path
        self._install_script = install_script
        self._service_name = service_name
        self._runner = runner

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
                args=["sudo", "git", "checkout", branch],
                cwd=self._repo_path,
                timeout_seconds=60,
            ),
            ApplyAttempt(
                label="git pull",
                args=["sudo", "git", "pull", "origin", branch],
                cwd=self._repo_path,
                timeout_seconds=180,
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
            ),
        )

    def _run_step(
        self, step: ApplyAttempt, on_step: Optional[StreamCallback],
    ) -> dict:
        if on_step:
            on_step(step.label, "started")
        try:
            rc, stdout, stderr = self._runner(
                step.args, step.cwd, step.timeout_seconds,
            )
        except subprocess.TimeoutExpired:
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
