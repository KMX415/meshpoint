"""Tests for the dangerous-action registry + handler factories."""

from __future__ import annotations

import unittest
from typing import Awaitable

from src.api.dangerous.actions import (
    DangerousAction,
    DangerousActionRegistry,
    DangerousActionResult,
)
from src.api.dangerous.handlers import (
    build_clear_database_action,
    build_force_nodeinfo_action,
    build_restart_concentrator_action,
    build_restart_service_action,
    build_wipe_phantoms_action,
)


class _RecorderRunner:
    def __init__(self, *, returncode: int = 0) -> None:
        self.calls: list[list[str]] = []
        self._rc = returncode

    def __call__(self, args, timeout):
        self.calls.append(list(args))
        return self._rc, "ok", ""


class _FakeFuture:
    def __init__(self, value) -> None:
        self._value = value

    def result(self, timeout: float = 0):
        if isinstance(self._value, Exception):
            raise self._value
        return self._value


class TestRegistry(unittest.TestCase):
    def test_invoke_unknown_returns_failure_result(self) -> None:
        registry = DangerousActionRegistry([])
        result = registry.invoke("nope")
        self.assertFalse(result.success)
        self.assertIn("unknown action", result.message)

    def test_invoke_runs_handler_and_returns_result(self) -> None:
        called = {"n": 0}

        def handler() -> DangerousActionResult:
            called["n"] += 1
            return DangerousActionResult(success=True, message="ok")

        action = DangerousAction(
            id="boom",
            label="Boom",
            description="…",
            confirmation_text="boom",
            handler=handler,
        )
        registry = DangerousActionRegistry([action])
        result = registry.invoke("boom")
        self.assertTrue(result.success)
        self.assertEqual(called["n"], 1)

    def test_invoke_catches_handler_exceptions(self) -> None:
        def handler() -> DangerousActionResult:
            raise RuntimeError("blew up")

        action = DangerousAction(
            id="fail",
            label="Fail",
            description="",
            confirmation_text="fail",
            handler=handler,
        )
        registry = DangerousActionRegistry([action])
        result = registry.invoke("fail")
        self.assertFalse(result.success)
        self.assertIn("handler raised", result.message)


class TestRestartHandlers(unittest.TestCase):
    def test_restart_service_runs_systemctl(self) -> None:
        runner = _RecorderRunner()
        action = build_restart_service_action(runner=runner)
        result = action.handler()
        self.assertTrue(result.success)
        self.assertEqual(runner.calls[0][:3], ["sudo", "systemctl", "restart"])

    def test_restart_service_failure_surfaced(self) -> None:
        runner = _RecorderRunner(returncode=1)
        action = build_restart_service_action(runner=runner)
        result = action.handler()
        self.assertFalse(result.success)

    def test_restart_concentrator_metadata_visible(self) -> None:
        action = build_restart_concentrator_action(runner=_RecorderRunner())
        self.assertEqual(action.confirmation_text, "restart")
        self.assertEqual(action.id, "restart_concentrator")


class TestAsyncDispatchHandlers(unittest.TestCase):
    def _dispatch_returning(self, value):
        def dispatch(coro: Awaitable):
            try:
                coro.close()
            except Exception:
                pass
            return _FakeFuture(value)
        return dispatch

    def test_clear_database_returns_count(self) -> None:
        async def coro():
            return 42
        action = build_clear_database_action(
            dispatch=self._dispatch_returning(42),
            clear_coro_factory=coro,
        )
        result = action.handler()
        self.assertTrue(result.success)
        self.assertEqual(result.details["removed"], 42)

    def test_wipe_phantoms_reports_count(self) -> None:
        async def coro():
            return 7
        action = build_wipe_phantoms_action(
            dispatch=self._dispatch_returning(7),
            wipe_coro_factory=coro,
        )
        result = action.handler()
        self.assertTrue(result.success)
        self.assertEqual(result.details["removed"], 7)

    def test_force_nodeinfo_handles_failure(self) -> None:
        async def coro():
            return False
        action = build_force_nodeinfo_action(
            dispatch=self._dispatch_returning(False),
            broadcast_coro_factory=coro,
        )
        result = action.handler()
        self.assertFalse(result.success)


if __name__ == "__main__":
    unittest.main()
