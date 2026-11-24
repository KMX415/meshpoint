"""Native TX owns airtime, not just the lgw_send call (#181)."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
import threading
import time
import unittest
from unittest.mock import Mock, patch

from src.config import TransmitConfig
from src.hal import sx1302_access as access
from src.hal.sx1302_types import LgwPktTxS
from src.hal.sx1302_wrapper import SX1302Wrapper
from src.transmit.tx_service import TxService


class HalTests(unittest.TestCase):
    def build(self, states):
        wrapper = SX1302Wrapper(lib_path="unused")
        wrapper._started = True
        wrapper._lib = Mock()
        wrapper._lib.lgw_time_on_air.return_value = 10
        wrapper._lib.lgw_send.return_value = 0
        iterator = iter(states)

        def status(chain, kind, output):
            output._obj.value = next(iterator)
            return 0
        wrapper._lib.lgw_status.side_effect = status
        return wrapper

    def test_waits_for_busy_before_send_and_completion_after(self):
        w = self.build([4, 3, 2, 4, 2])
        with patch.object(access.time, "sleep"):
            self.assertEqual(w.send(LgwPktTxS()), 0)
        self.assertEqual(w._lib.lgw_status.call_count, 5)
        w._lib.lgw_send.assert_called_once()

    def test_status_failure_never_sends(self):
        w = self.build([])
        w._lib.lgw_status.side_effect = None
        w._lib.lgw_status.return_value = -1
        self.assertEqual(w.send(LgwPktTxS()), -1)
        w._lib.lgw_send.assert_not_called()

    def test_busy_timeout_never_sends(self):
        w = self.build([4] * 10)
        with patch.object(access, "BUSY_TIMEOUT_SECONDS", .01):
            self.assertEqual(w.send(LgwPktTxS()), -1)
        w._lib.lgw_send.assert_not_called()

    def test_never_reports_success_if_completion_stays_busy(self):
        w = self.build([2] + [4] * 10)
        with patch.object(access.time, "monotonic", side_effect=[0, 0, 1, 2, 3, 4]), patch.object(access.time, "sleep"):
            self.assertEqual(w.send(LgwPktTxS()), -1)

    def test_initial_free_is_not_immediate_completion(self):
        w = self.build([2, 2, 4, 2])
        with patch.object(access.time, "monotonic", return_value=0), patch.object(access.time, "sleep"):
            self.assertEqual(w.send(LgwPktTxS()), 0)
        self.assertEqual(w._lib.lgw_status.call_count, 4)

    def test_short_packet_completed_between_polls(self):
        w = self.build([2, 2])
        with patch.object(access.time, "monotonic", side_effect=[0, 0, .02]):
            self.assertEqual(w.send(LgwPktTxS()), 0)

    def test_restart_during_send_is_not_success(self):
        w = self.build([2])
        def sent(packet):
            w._generation += 1
            return 0
        w._lib.lgw_send.side_effect = sent
        # Generation is taken after the send, so simulate a restart at sleep.
        w._lib.lgw_status.side_effect = lambda c, k, out: (setattr(out._obj, "value", 2), 0)[1]
        with patch.object(access.time, "sleep", side_effect=lambda _: setattr(w, "_generation", w._generation + 1)):
            self.assertEqual(w.send(LgwPktTxS()), -1)

    def test_concurrent_senders_do_not_overlap_and_receive_can_poll(self):
        w = self.build([])
        end = [0.0]
        sends, overlaps, receives = [], [], []
        call_guard = threading.Lock()
        concurrent_hal = []
        def guarded(fn):
            def call(*args):
                if not call_guard.acquire(False):
                    concurrent_hal.append(True)
                    call_guard.acquire()
                try:
                    time.sleep(.001)
                    return fn(*args)
                finally:
                    call_guard.release()
            return call
        def status(c, k, out):
            out._obj.value = 4 if time.monotonic() < end[0] else 2
            return 0
        def send(packet):
            now = time.monotonic()
            overlaps.append(now < end[0])
            sends.append(now)
            end[0] = now + .04
            return 0
        w._lib.lgw_status.side_effect = guarded(status)
        w._lib.lgw_send.side_effect = guarded(send)
        w._lib.lgw_receive.side_effect = guarded(lambda *args: (receives.append(time.monotonic()), 0)[1])
        w._lib.lgw_time_on_air.side_effect = guarded(lambda *args: 40)
        with ThreadPoolExecutor(max_workers=3) as pool:
            a = pool.submit(w.send, LgwPktTxS())
            b = pool.submit(w.send, LgwPktTxS())
            deadline = time.monotonic() + 1
            while not (a.done() and b.done()) and time.monotonic() < deadline:
                w.receive()
                time.sleep(.002)
            self.assertEqual([a.result(timeout=1), b.result(timeout=1)], [0, 0])
        self.assertEqual(overlaps, [False, False])
        self.assertFalse(concurrent_hal)
        self.assertTrue(any(sends[0] < t < sends[1] for t in receives))


class ServiceTests(unittest.IsolatedAsyncioTestCase):
    def service(self):
        self.entered = threading.Event()
        self.release = threading.Event()
        self.calls = []
        def send(packet):
            self.calls.append(packet)
            self.entered.set()
            if not self.release.wait(2):
                raise RuntimeError("test release timed out")
            return 0
        self.wrapper = Mock(send=send)
        self.wrapper.get_time_on_air.return_value = 10
        self.duty = Mock()
        self.duty.check_budget.return_value = True
        svc = TxService(wrapper=self.wrapper, transmit_config=TransmitConfig(enabled=True, node_id=0x12345678),
                        duty_tracker=self.duty, persist_derived_node_id=False)
        return svc

    async def test_cancelled_request_does_not_release_tx_or_skip_accounting(self):
        svc = self.service()
        first = asyncio.create_task(svc._send_native(LgwPktTxS(), 10))
        self.assertTrue(await asyncio.to_thread(self.entered.wait, 1))
        first.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await first
        second = asyncio.create_task(svc._send_native(LgwPktTxS(), 10))
        await asyncio.sleep(.02)
        self.assertEqual(len(self.calls), 1)
        self.release.set()
        self.assertEqual(await asyncio.wait_for(second, 1), 0)
        self.assertEqual(self.duty.record_tx.call_count, 2)

    async def test_budget_is_rechecked_after_waiting(self):
        svc = self.service()
        first = asyncio.create_task(svc._send_native(LgwPktTxS(), 10))
        self.assertTrue(await asyncio.to_thread(self.entered.wait, 1))
        second = asyncio.create_task(svc._send_native(LgwPktTxS(), 10))
        self.duty.record_tx.side_effect = lambda _: setattr(self.duty.check_budget, "return_value", False)
        self.release.set()
        self.assertEqual(await first, 0)
        self.assertEqual(await second, -2)
        self.assertEqual(len(self.calls), 1)

    async def test_all_native_entry_points_share_arbitration(self):
        svc = self.service()
        self.release.set()
        frame = bytes(12) + bytes([3, 0, 0, 0]) + b"test"
        builder = Mock()
        builder.build_nodeinfo.return_value = frame
        builder.build_text_message.return_value = frame
        svc._get_builder = Mock(return_value=builder)
        svc._resolve_channel = Mock(return_value=(0, b""))
        results = await asyncio.gather(
            svc.send_nodeinfo("test", "test"),
            svc.send_text("test", destination="broadcast"),
            svc._send_built_packet(frame, 1, label="position"),
            svc.send_raw_relay(frame),
        )
        self.assertTrue(all(r.success for r in results))
        self.assertEqual(len(self.calls), 4)
        self.assertEqual(self.duty.record_tx.call_count, 4)
