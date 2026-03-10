"""Tests for src/remote/command_handler.py -- dispatch and confirmation gating."""

import asyncio
import unittest

from src.remote.command_handler import CommandHandler


def _sync_executor(params):
    return {"echo": params.get("msg", "ok")}


async def _async_executor(params):
    return {"async": True}


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


class TestDispatch(unittest.TestCase):

    def setUp(self):
        self.handler = CommandHandler()
        self.handler.register("ping", _sync_executor)
        self.handler.register("async_cmd", _async_executor)

    def test_dispatch_sync_executor(self):
        msg = {"command_id": "c1", "action": "ping", "params": {"msg": "hello"}}
        result = _run(self.handler.handle(msg))
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["data"]["echo"], "hello")
        self.assertEqual(result["command_id"], "c1")

    def test_dispatch_async_executor(self):
        msg = {"command_id": "c2", "action": "async_cmd", "params": {}}
        result = _run(self.handler.handle(msg))
        self.assertEqual(result["status"], "success")
        self.assertTrue(result["data"]["async"])

    def test_unknown_action_returns_error(self):
        msg = {"command_id": "c3", "action": "bogus"}
        result = _run(self.handler.handle(msg))
        self.assertEqual(result["status"], "error")
        self.assertIn("Unknown action", result["data"]["error"])

    def test_missing_action_returns_error(self):
        msg = {"command_id": "c4"}
        result = _run(self.handler.handle(msg))
        self.assertEqual(result["status"], "error")
        self.assertIn("Missing action", result["data"]["error"])


class TestConfirmationGating(unittest.TestCase):

    def setUp(self):
        self.handler = CommandHandler()
        self.handler.register("restart_service", _sync_executor)
        self.handler.register("apply_update", _sync_executor)

    def test_dangerous_action_without_confirm_returns_confirm_required(self):
        msg = {"command_id": "c5", "action": "restart_service"}
        result = _run(self.handler.handle(msg))
        self.assertEqual(result["status"], "confirm_required")
        self.assertIn("confirm", result["data"]["message"])

    def test_dangerous_action_with_confirm_false_returns_confirm_required(self):
        msg = {"command_id": "c6", "action": "apply_update", "confirm": False}
        result = _run(self.handler.handle(msg))
        self.assertEqual(result["status"], "confirm_required")

    def test_dangerous_action_with_confirm_true_executes(self):
        msg = {"command_id": "c7", "action": "restart_service", "confirm": True}
        result = _run(self.handler.handle(msg))
        self.assertEqual(result["status"], "success")


class TestExecutorException(unittest.TestCase):

    def setUp(self):
        self.handler = CommandHandler()
        self.handler.register("fail", self._failing_executor)

    @staticmethod
    def _failing_executor(params):
        raise RuntimeError("boom")

    def test_executor_exception_returns_error(self):
        msg = {"command_id": "c8", "action": "fail"}
        result = _run(self.handler.handle(msg))
        self.assertEqual(result["status"], "error")
        self.assertIn("boom", result["data"]["error"])


if __name__ == "__main__":
    unittest.main()
