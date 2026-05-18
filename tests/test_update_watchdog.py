"""Tests for the watchdog auto-rollback monitor."""

from __future__ import annotations

import unittest

from src.api.update.watchdog import (
    RollbackTag,
    WatchdogMonitor,
    make_rollback_tag,
)


class TestWatchdogMonitor(unittest.TestCase):
    def _make_tag(self) -> RollbackTag:
        return RollbackTag(sha="abc123", branch="main", captured_at=0.0)

    def test_returns_true_when_healthy_streak_lands(self) -> None:
        probes = iter([False, True, True, True])
        rollbacks: list[str] = []
        monitor = WatchdogMonitor(
            probe=lambda: next(probes),
            rollback_handler=lambda sha: rollbacks.append(sha),
            poll_interval_seconds=0,
            max_polls=10,
            healthy_streak=3,
            sleep_func=lambda _s: None,
        )
        self.assertTrue(monitor.watch(self._make_tag()))
        self.assertEqual(rollbacks, [])

    def test_rollback_invoked_when_budget_exhausted(self) -> None:
        rollbacks: list[str] = []
        monitor = WatchdogMonitor(
            probe=lambda: False,
            rollback_handler=lambda sha: rollbacks.append(sha),
            poll_interval_seconds=0,
            max_polls=3,
            healthy_streak=2,
            sleep_func=lambda _s: None,
        )
        self.assertFalse(monitor.watch(self._make_tag()))
        self.assertEqual(rollbacks, ["abc123"])

    def test_streak_resets_on_unhealthy_probe(self) -> None:
        # Two healthy probes, a single bad probe, then exhaustion.
        # The streak (which needs 3 healthy in a row) never lands, so
        # the watchdog must roll back when the budget runs out.
        sequence = [True, True, False] + [True, True]
        rollbacks: list[str] = []
        index = {"i": 0}

        def probe() -> bool:
            i = index["i"]
            index["i"] = i + 1
            return sequence[i] if i < len(sequence) else False

        monitor = WatchdogMonitor(
            probe=probe,
            rollback_handler=lambda sha: rollbacks.append(sha),
            poll_interval_seconds=0,
            max_polls=5,
            healthy_streak=3,
            sleep_func=lambda _s: None,
        )
        self.assertFalse(monitor.watch(self._make_tag()))
        self.assertEqual(rollbacks, ["abc123"])

    def test_make_rollback_tag_returns_none_for_empty_sha(self) -> None:
        self.assertIsNone(make_rollback_tag(None))
        self.assertIsNone(make_rollback_tag(""))

    def test_make_rollback_tag_accepts_sha(self) -> None:
        tag = make_rollback_tag("abc", branch="main")
        self.assertIsNotNone(tag)
        self.assertEqual(tag.sha, "abc")
        self.assertEqual(tag.branch, "main")


if __name__ == "__main__":
    unittest.main()
