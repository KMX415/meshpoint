"""Tests for ``UpdateApplier`` using a fake :data:`Runner`.

The applier is unit-testable because subprocess invocation is
delegated; we plug in a recorder runner that returns canned
exit codes and captures the command list for assertion.
"""

from __future__ import annotations

import unittest
from typing import Optional

from src.api.update.apply import (
    ApplyAttempt,
    UpdateApplier,
)


class _RecorderRunner:
    """Test double for :data:`src.api.update.apply.Runner`."""

    def __init__(self, *, fail_at: Optional[str] = None) -> None:
        self.calls: list[list[str]] = []
        self.cwds: list[Optional[str]] = []
        self._fail_at = fail_at

    def __call__(
        self, args: list[str], cwd: Optional[str], timeout_seconds: float,
    ) -> tuple[int, str, str]:
        self.calls.append(list(args))
        self.cwds.append(cwd)
        if args[:2] == ["git", "rev-parse"]:
            return 0, "abc123\n", ""
        if self._fail_at and self._fail_at in " ".join(args):
            return 1, "", "boom"
        return 0, "ok", ""


class TestUpdateApplier(unittest.TestCase):
    def test_apply_runs_full_chain_in_order(self) -> None:
        runner = _RecorderRunner()
        applier = UpdateApplier(runner=runner, repo_path=".")
        result = applier.apply(branch="main")
        self.assertTrue(result.success)
        self.assertEqual(result.target_branch, "main")
        self.assertEqual(result.pre_update_sha, "abc123")
        labels = [entry["step"] for entry in result.log]
        self.assertEqual(
            labels,
            [
                "git fetch",
                "git checkout",
                "git pull",
                "install.sh",
                "restart service",
            ],
        )

    def test_apply_stops_on_first_failure(self) -> None:
        runner = _RecorderRunner(fail_at="checkout")
        applier = UpdateApplier(runner=runner, repo_path=".")
        result = applier.apply(branch="main")
        self.assertFalse(result.success)
        self.assertEqual(result.failed_step, "git checkout")
        labels = [entry["step"] for entry in result.log]
        self.assertEqual(labels, ["git fetch", "git checkout"])

    def test_apply_streams_each_step_via_callback(self) -> None:
        runner = _RecorderRunner()
        applier = UpdateApplier(runner=runner, repo_path=".")
        events: list[tuple[str, str]] = []
        applier.apply(
            branch="main",
            on_step=lambda label, state: events.append((label, state)),
        )
        starts = [e for e in events if e[1] == "started"]
        completions = [e for e in events if e[1] == "completed"]
        self.assertEqual(len(starts), 5)
        self.assertEqual(len(completions), 5)

    def test_rollback_runs_reset_then_restart(self) -> None:
        runner = _RecorderRunner()
        applier = UpdateApplier(runner=runner, repo_path=".")
        result = applier.rollback(sha="deadbeef")
        self.assertTrue(result.success)
        steps = [entry["step"] for entry in result.log]
        self.assertEqual(steps, ["git reset", "restart service"])
        self.assertIn("deadbeef", " ".join(runner.calls[0]))

    def test_rollback_failure_returns_failed_step(self) -> None:
        runner = _RecorderRunner(fail_at="reset")
        applier = UpdateApplier(runner=runner, repo_path=".")
        result = applier.rollback(sha="deadbeef")
        self.assertFalse(result.success)
        self.assertEqual(result.failed_step, "git reset")


if __name__ == "__main__":
    unittest.main()
