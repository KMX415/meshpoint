"""The upstream reconnect loop logs expected transient network failures as
a single warning line, not a full traceback on every retry.

Regression for the "upstream can't connect and it looks stuck" report: the
app was never stuck (packets kept flowing, the loop kept retrying), but
`logger.exception` dumped a ~20-line stack trace every reconnect attempt,
which reads as a crash loop when tailing the log.
"""

from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, patch

from websockets.exceptions import InvalidHandshake

from src.api.upstream_client import UpstreamClient
from src.config import UpstreamConfig
from src.models.device_identity import DeviceIdentity


def _client() -> UpstreamClient:
    client = UpstreamClient(
        UpstreamConfig(enabled=True, url="wss://upstream.example.invalid", auth_token="t"),
        DeviceIdentity(device_id="dev-1"),
    )
    client._reconnect_delay = 0  # no real backoff sleep in the test
    return client


class TestUpstreamReconnectLogging(unittest.IsolatedAsyncioTestCase):
    async def _run_loop_with_failure(self, exc: BaseException):
        client = _client()
        attempts = []

        async def fake_connect_and_run():
            attempts.append(1)
            if len(attempts) >= 2:
                client._running = False  # let the loop exit after 2 tries
            raise exc

        client._connect_and_run = fake_connect_and_run
        client._running = True
        with self.assertLogs("src.api.upstream_client", level="WARNING") as cm:
            await client._connection_loop()
        return attempts, cm.output

    async def test_no_route_to_host_is_a_one_line_warning(self):
        attempts, output = await self._run_loop_with_failure(
            OSError(113, "No route to host")
        )
        self.assertEqual(len(attempts), 2)  # loop kept retrying, not stuck
        self.assertTrue(any("connection failed" in m for m in output))
        self.assertTrue(any("OSError" in m and "No route to host" in m for m in output))
        # not logged at ERROR / not a traceback
        self.assertFalse(any(m.startswith("ERROR") for m in output))
        self.assertFalse(any("Traceback" in m for m in output))

    async def test_connection_refused_is_a_one_line_warning(self):
        _, output = await self._run_loop_with_failure(
            ConnectionRefusedError(111, "Connection refused")
        )
        self.assertTrue(any("connection failed" in m for m in output))
        self.assertFalse(any("Traceback" in m for m in output))

    async def test_timeout_and_handshake_failures_are_warnings(self):
        for exc in (TimeoutError("timeout"), InvalidHandshake("rejected")):
            with self.subTest(error=type(exc).__name__):
                attempts, output = await self._run_loop_with_failure(exc)
                self.assertEqual(len(attempts), 2)
                self.assertTrue(any("connection failed" in m for m in output))
                self.assertFalse(any("Traceback" in m for m in output))

    async def test_retry_backoff_and_buffer_are_preserved(self):
        client = _client()
        client._reconnect_delay = 2
        client._running = True
        client._buffer.append({"type": "test"})
        attempts = 0

        async def fail_then_stop():
            nonlocal attempts
            attempts += 1
            if attempts == 4:
                client._running = False
            raise ConnectionRefusedError("refused")

        client._connect_and_run = fail_then_stop
        with patch("src.api.upstream_client.asyncio.sleep", new_callable=AsyncMock) as sleep:
            with self.assertLogs("src.api.upstream_client", level="WARNING"):
                await client._connection_loop()
        self.assertEqual([call.args[0] for call in sleep.await_args_list], [2, 3, 4.5])
        self.assertEqual(list(client._buffer), [{"type": "test"}])
        self.assertFalse(client._connected)

    async def test_unexpected_error_still_logs_a_traceback(self):
        _, output = await self._run_loop_with_failure(ValueError("bug"))
        # a genuine bug must still surface loudly
        self.assertTrue(any(m.startswith("ERROR") for m in output))
        self.assertTrue(any("connection error" in m for m in output))
        self.assertTrue(any("Traceback" in m for m in output))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
