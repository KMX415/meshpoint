"""Tests for meshtasticd bridge capture source."""

import asyncio
import unittest
from unittest.mock import MagicMock, patch

from src.capture.meshtasticd_bridge_source import MeshtasticdBridgeSource


class TestMeshtasticdBridgeSource(unittest.TestCase):
    def test_name_is_meshtasticd(self):
        src = MeshtasticdBridgeSource()
        self.assertEqual(src.name, "meshtasticd")

    def test_connect_subscribes_and_sets_interface(self):
        src = MeshtasticdBridgeSource(host="127.0.0.1", port=4403)
        fake_iface = MagicMock()

        with patch("meshtastic.tcp_interface.TCPInterface", return_value=fake_iface):
            with patch("pubsub.pub.subscribe") as mock_sub:
                src._connect_blocking()

        self.assertIs(src.interface, fake_iface)
        mock_sub.assert_called_once()

    def test_on_receive_enqueues_packet(self):
        src = MeshtasticdBridgeSource()
        src._running = True
        packet = {"raw": "0102030405060708090a0b0c0d0e0f10", "rxRssi": -88}

        src._on_receive(packet, None)

        queued = src._queue.get_nowait()
        self.assertEqual(queued.capture_source, "meshtasticd")


class TestMeshtasticdBridgeAsync(unittest.IsolatedAsyncioTestCase):
    async def test_start_sets_running_when_connect_succeeds(self):
        src = MeshtasticdBridgeSource(connect_attempts=1)

        def _connect_ok():
            src._interface = MagicMock()

        with patch.object(src, "_connect_blocking", side_effect=_connect_ok):
            await src.start()

        self.assertTrue(src._running)
        self.assertIsNotNone(src.interface)

    async def test_start_raises_when_connect_exhausted(self):
        src = MeshtasticdBridgeSource(
            connect_attempts=2,
            connect_delay_seconds=0.01,
        )

        with patch.object(
            src,
            "_connect_blocking",
            side_effect=RuntimeError("down"),
        ):
            with self.assertRaises(RuntimeError):
                await src.start()


if __name__ == "__main__":
    unittest.main()
