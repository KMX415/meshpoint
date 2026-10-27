"""Tests for meshtasticd bridge capture source."""

import asyncio
import queue
import unittest
from unittest.mock import MagicMock, patch

from src.capture.meshtasticd_bridge_source import MeshtasticdBridgeSource


class TestMeshtasticdBridgeSource(unittest.TestCase):
    def test_name_is_meshtasticd(self):
        src = MeshtasticdBridgeSource()
        self.assertEqual(src.name, "meshtasticd")

    def test_request_send_text_requires_worker(self):
        src = MeshtasticdBridgeSource()
        success, error = src.request_send_text("hi", 0xFFFFFFFF)
        self.assertFalse(success)
        self.assertIn("not connected", error or "")


class TestMeshtasticdBridgeAsync(unittest.IsolatedAsyncioTestCase):
    async def test_start_sets_running_when_worker_ready(self):
        src = MeshtasticdBridgeSource(connect_attempts=1)
        fake_process = MagicMock()
        fake_process.pid = 1234
        fake_process.is_alive.return_value = True

        with patch("src.capture.meshtasticd_bridge_source.wait_for_tcp_port"):
            with patch.object(src, "_start_worker") as mock_start:
                def _ready():
                    src._worker = fake_process

                mock_start.side_effect = _ready
                await src.start()

        self.assertTrue(src._running)
        self.assertTrue(src.is_running)

    async def test_start_raises_when_worker_start_fails(self):
        src = MeshtasticdBridgeSource(
            connect_attempts=2,
            connect_delay_seconds=0.01,
        )

        with patch("src.capture.meshtasticd_bridge_source.wait_for_tcp_port"):
            with patch.object(
                src,
                "_start_worker",
                side_effect=RuntimeError("down"),
            ):
                with self.assertRaises(RuntimeError):
                    await src.start()

    async def test_packets_yields_from_worker_queue(self):
        src = MeshtasticdBridgeSource()
        src._running = True
        src._worker = MagicMock()
        src._worker.is_alive.return_value = True
        src._pkt_queue = MagicMock()
        raw = MagicMock()
        src._pkt_queue.get.side_effect = [raw, queue.Empty()]

        async def _run():
            packets = []
            async for packet in src.packets():
                packets.append(packet)
                break
            return packets

        with patch("asyncio.to_thread", side_effect=lambda fn, *args, **kwargs: fn(*args, **kwargs)):
            result = await asyncio.wait_for(_run(), timeout=2.0)

        self.assertEqual(result, [raw])


if __name__ == "__main__":
    unittest.main()
