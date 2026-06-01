"""Run the multi-step update from the dashboard.

The applier walks ``git fetch`` -> ``git checkout -f`` -> ``git reset
--hard origin/<branch>`` -> ``pip install -r requirements.txt`` ->
detached ``apply_finish.sh`` (``systemctl stop`` -> ``install.sh`` ->
``systemctl restart``). Git and pip run while the service is still up
so the HTTP stream can finish; stopping first would kill this process
mid-chain. ``apply_finish.sh`` runs in a new session so the stop does
not abort the applier before dependencies are installed.

Each synchronous step is its own subprocess invocation so the dashboard
can stream a running log to the operator and so a step that exits
non-zero stops the chain immediately with the failing step labelled.

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

from src.api.dangerous.handlers import (
    schedule_detached_apply_finish,
    schedule_systemctl_restart,
)
from src.api.update.install_status import read_head_full_sha
from src.api.update.rollback_state import (
    DEFAULT_ROLLBACK_STATE_PATH,
    write_rollback_state,
)

logger = logging.getLogger(__name__)


@dataclass
class ApplyAttempt:
    """One step in the apply chain."""

    label: str
    args: list[str]
    cwd: Optional[str] = None
    timeout_seconds: float = 600.0
    detached: bool = False
    finish_script: Optional[str] = None


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
StreamCallback = Callable[[str, str, Optional[dict]], None]


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
        finish_script: str = "/opt/meshpoint/scripts/apply_finish.sh",
        service_name: str = "meshpoint",
        runner: Runner = shell_runner,
        rollback_state_path: Path | None = None,
    ) -> None:
        self._repo_path = repo_path
        self._install_script = install_script
        self._finish_script = finish_script
        self._service_name = service_name
        self._runner = runner
        self._rollback_state_path = (
            rollback_state_path or DEFAULT_ROLLBACK_STATE_PATH
        )

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
        if pre_sha:
            # Persist before mutating the tree. The apply stream often dies when
            # systemctl restart drops the HTTP connection; route-level persist
            # on the final NDJSON line then never runs.
            if not write_rollback_state(
                pre_sha,
                target_branch=branch,
                path=self._rollback_state_path,
            ):
                logger.error(
                    "apply: rollback state not saved under %s",
                    self._rollback_state_path,
                )
        else:
            logger.error(
                "apply: could not capture pre-update SHA in %s; "
                "dashboard rollback will stay disabled for this run",
                self._repo_path,
            )
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
        pip_path = f"{self._repo_path}/venv/bin/pip"
        requirements_path = f"{self._repo_path}/requirements.txt"
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
                label="pip install",
                args=[
                    "sudo",
                    pip_path,
                    "install",
                    "-r",
                    requirements_path,
                ],
                timeout_seconds=600,
            ),
            ApplyAttempt(
                label="finish install",
                args=["sudo", "bash", self._finish_script],
                timeout_seconds=60,
                detached=True,
                finish_script=self._finish_script,
            ),
        )

    def _run_step(
        self, step: ApplyAttempt, on_step: Optional[StreamCallback],
    ) -> dict:
        started_detail = {"command": shlex.join(step.args)}
        if on_step:
            on_step(step.label, "started", started_detail)
        if step.detached:
            if step.finish_script:
                proc = schedule_detached_apply_finish(step.finish_script)
            else:
                proc = schedule_systemctl_restart(self._service_name)
            entry = {
                "step": step.label,
                "command": shlex.join(step.args),
                "returncode": 0,
                "stdout": "",
                "stderr": "",
                "detached": True,
                "pid": proc.pid,
            }
            if on_step:
                on_step(step.label, "completed", _public_step_detail(entry))
            return entry
        try:
            rc, stdout, stderr = self._runner(
                step.args, step.cwd, step.timeout_seconds,
            )
        except subprocess.TimeoutExpired:
            entry = {
                "step": step.label,
                "command": shlex.join(step.args),
                "returncode": -1,
                "stdout": "",
                "stderr": "timeout",
            }
            if on_step:
                on_step(step.label, "error", _public_step_detail(entry))
            return entry
        entry = {
            "step": step.label,
            "command": shlex.join(step.args),
            "returncode": rc,
            "stdout": stdout,
            "stderr": stderr,
        }
        if on_step:
            on_step(
                step.label,
                "completed" if rc == 0 else "error",
                _public_step_detail(entry),
            )
        return entry

    def _capture_head_sha(self) -> Optional[str]:
        if not Path(self._repo_path).exists():
            return None
        try:
            return read_head_full_sha(
                self._repo_path,
                runner=self._runner,
                use_sudo=True,
            )
        except Exception:
            logger.warning(
                "failed to capture pre-update SHA in %s",
                self._repo_path,
                exc_info=True,
            )
        return None


def _public_step_detail(entry: dict) -> dict:
    """Trim step output for NDJSON streaming to the dashboard."""
    detail: dict = {
        "command": entry.get("command", ""),
        "returncode": entry.get("returncode"),
    }
    if entry.get("detached"):
        detail["detached"] = True
        detail["note"] = (
            "Continues in background: stop service, run install.sh, restart."
        )
    stdout = (entry.get("stdout") or "").strip()
    stderr = (entry.get("stderr") or "").strip()
    if stdout:
        detail["stdout"] = stdout[-4000:] if len(stdout) > 4000 else stdout
    if stderr:
        detail["stderr"] = stderr[-4000:] if len(stderr) > 4000 else stderr
    return detail
