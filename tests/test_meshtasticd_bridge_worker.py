"""Tests for meshtasticd bridge worker reconnect scheduling."""

import queue
import unittest
from unittest.mock import MagicMock, patch

from src.capture.meshtasticd_bridge_ipc import BridgeCommand
from src.capture.meshtasticd_bridge_worker import _BridgeWorker, _STALL_RECONNECT_SECONDS


class TestBridgeWorkerReconnectScheduling(unittest.TestCase):
    def test_watchdog_queues_reconnect_instead_of_calling_directly(self):
        worker = _BridgeWorker(
            host="127.0.0.1",
            port=4403,
            default_frequency_mhz=906.875,
            pkt_queue=MagicMock(),
            cmd_queue=queue.Queue(),
            resp_queue=queue.Queue(),
            sync_settings_dict=None,
        )
        worker._running = True
        worker._iface = MagicMock()
        worker._iface._rxThread = MagicMock()
        worker._iface._rxThread.is_alive.return_value = True
        worker._last_packet_at = 0.0
        worker._iface_op_in_progress = False

        with patch.object(worker, "_schedule_reconnect") as schedule:
            rx_thread = worker._iface._rxThread
            if rx_thread is not None and not rx_thread.is_alive():
                worker._schedule_reconnect("reader thread exited")
            import time

            worker._last_packet_at = time.monotonic() - (_STALL_RECONNECT_SECONDS + 5)
            idle = time.monotonic() - worker._last_packet_at
            if idle >= _STALL_RECONNECT_SECONDS and not worker._iface_op_in_progress:
                worker._schedule_reconnect(f"no packets for {idle:.0f}s")

        schedule.assert_called_once()
        args, _ = schedule.call_args
        self.assertIn("no packets for", args[0])

    def test_watchdog_skips_idle_reconnect_during_iface_op(self):
        worker = _BridgeWorker(
            host="127.0.0.1",
            port=4403,
            default_frequency_mhz=906.875,
            pkt_queue=MagicMock(),
            cmd_queue=queue.Queue(),
            resp_queue=queue.Queue(),
            sync_settings_dict=None,
        )
        worker._running = True
        worker._iface = MagicMock()
        worker._iface._rxThread.is_alive.return_value = True
        worker._iface_op_in_progress = True
        worker._last_packet_at = 0.0

        with patch.object(worker, "_schedule_reconnect") as schedule:
            import time

            idle = time.monotonic() - worker._last_packet_at
            if idle >= _STALL_RECONNECT_SECONDS and not worker._iface_op_in_progress:
                worker._schedule_reconnect(f"no packets for {idle:.0f}s")

        schedule.assert_not_called()

    def test_schedule_reconnect_enqueues_command(self):
        cmd_q: queue.Queue = queue.Queue()
        worker = _BridgeWorker(
            host="127.0.0.1",
            port=4403,
            default_frequency_mhz=906.875,
            pkt_queue=MagicMock(),
            cmd_queue=cmd_q,
            resp_queue=queue.Queue(),
            sync_settings_dict=None,
        )
        worker._schedule_reconnect("test reason")
        op, payload = cmd_q.get_nowait()
        self.assertEqual(op, BridgeCommand.RECONNECT)
        self.assertEqual(payload, "test reason")


if __name__ == "__main__":
    unittest.main()
