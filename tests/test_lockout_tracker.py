"""Unit tests for ``src.api.auth.lockout_tracker``.

Uses a hand-driven monotonic clock so the suite never sleeps.
"""

from __future__ import annotations

import unittest

from src.api.auth.lockout_tracker import LockoutTracker


class _FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class TestLockoutTracker(unittest.TestCase):
    def setUp(self) -> None:
        self.clock = _FakeClock()
        self.tracker = LockoutTracker(
            max_attempts=3, cooldown_minutes=5, clock=self.clock
        )

    def test_starts_unlocked(self) -> None:
        self.assertIsNone(self.tracker.remaining_seconds("admin"))

    def test_failures_under_threshold_do_not_lock(self) -> None:
        self.assertIsNone(self.tracker.register_failure("admin"))
        self.assertIsNone(self.tracker.register_failure("admin"))
        self.assertIsNone(self.tracker.remaining_seconds("admin"))

    def test_failures_at_threshold_lock(self) -> None:
        self.tracker.register_failure("admin")
        self.tracker.register_failure("admin")
        cooldown = self.tracker.register_failure("admin")
        self.assertEqual(cooldown, 300)
        remaining = self.tracker.remaining_seconds("admin")
        self.assertIsNotNone(remaining)
        assert remaining is not None
        self.assertGreater(remaining, 0)
        self.assertLessEqual(remaining, 301)

    def test_register_success_clears_failures(self) -> None:
        self.tracker.register_failure("admin")
        self.tracker.register_failure("admin")
        self.tracker.register_success("admin")
        self.assertIsNone(self.tracker.register_failure("admin"))
        self.assertIsNone(self.tracker.remaining_seconds("admin"))

    def test_lock_clears_after_cooldown_elapses(self) -> None:
        for _ in range(3):
            self.tracker.register_failure("admin")
        self.assertIsNotNone(self.tracker.remaining_seconds("admin"))
        self.clock.advance(301)
        self.assertIsNone(self.tracker.remaining_seconds("admin"))

    def test_keys_are_isolated(self) -> None:
        for _ in range(3):
            self.tracker.register_failure("admin")
        self.assertIsNotNone(self.tracker.remaining_seconds("admin"))
        self.assertIsNone(self.tracker.remaining_seconds("viewer"))
        self.assertIsNone(self.tracker.register_failure("viewer"))

    def test_failure_during_lock_returns_remaining_cooldown(self) -> None:
        for _ in range(3):
            self.tracker.register_failure("admin")
        self.clock.advance(120)
        residual = self.tracker.register_failure("admin")
        self.assertIsNotNone(residual)
        assert residual is not None
        self.assertGreater(residual, 0)
        self.assertLessEqual(residual, 181)

    def test_empty_key_is_noop(self) -> None:
        self.assertIsNone(self.tracker.register_failure(""))
        self.assertIsNone(self.tracker.remaining_seconds(""))
        self.tracker.register_success("")

    def test_constructor_validation(self) -> None:
        with self.assertRaises(ValueError):
            LockoutTracker(max_attempts=0, cooldown_minutes=5)
        with self.assertRaises(ValueError):
            LockoutTracker(max_attempts=5, cooldown_minutes=0)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
