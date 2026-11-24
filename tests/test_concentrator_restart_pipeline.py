"""Tests for in-process concentrator pipeline restart."""

from __future__ import annotations

import asyncio
import unittest
from unittest import mock

from src.capture.concentrator_source import ConcentratorCaptureSource


class TestConcentratorRestartPipeline(unittest.IsolatedAsyncioTestCase):
    async def test_restart_stops_then_starts_hal(self) -> None:
        wrapper = mock.Mock()
        wrapper.stop = mock.Mock()
        wrapper.reset = mock.Mock()
        wrapper.configure = mock.Mock()
        wrapper.start = mock.Mock()
        wrapper.set_syncword = mock.Mock()
        wrapper.load = mock.Mock()

        source = ConcentratorCaptureSource()
        source._wrapper = wrapper
        source._running = True
        source._syncword = 0x2B
        source._channel_plan = mock.Mock()

        async def fake_start() -> None:
            source._running = True

        with mock.patch.object(
            source, "start", side_effect=fake_start,
        ) as mock_start:
            await source.restart_pipeline()

        wrapper.stop.assert_called_once()
        mock_start.assert_awaited_once()
        self.assertTrue(source._running)


    async def test_existing_consumer_resumes_after_restart(self):
        source = ConcentratorCaptureSource()
        source._running = True
        source._poll_interval = 0.001
        source._wrapper = mock.Mock()
        source._wrapper.receive.return_value = []
        entered, release = asyncio.Event(), asyncio.Event()

        async def start():
            entered.set()
            await release.wait()
            source._running = True

        async def consume():
            async for _ in source.packets():
                pass

        consumer = asyncio.create_task(consume())
        await asyncio.sleep(0.01)
        with mock.patch.object(source, "start", side_effect=start):
            restart = asyncio.create_task(source.restart_pipeline())
            await asyncio.wait_for(entered.wait(), 1)
            polls = source._wrapper.receive.call_count
            await asyncio.sleep(0.01)
            self.assertFalse(consumer.done())
            self.assertEqual(source._wrapper.receive.call_count, polls)
            release.set()
            await restart
        await asyncio.sleep(0.01)
        self.assertGreater(source._wrapper.receive.call_count, polls)
        await source.stop()
        await asyncio.wait_for(consumer, 1)

    async def test_failed_restart_stops_consumer_and_clears_pause(self):
        source = ConcentratorCaptureSource()
        source._running = True
        source._wrapper = mock.Mock()
        source._wrapper.receive.return_value = []

        async def consume():
            async for _ in source.packets():
                pass

        consumer = asyncio.create_task(consume())
        with mock.patch.object(source, "start", side_effect=RuntimeError("start failed")):
            with self.assertRaisesRegex(RuntimeError, "start failed"):
                await source.restart_pipeline()
        await asyncio.wait_for(consumer, 1)
        self.assertFalse(source._running)
        self.assertFalse(source._restarting)

    async def test_stop_during_restart_leaves_source_stopped(self):
        source = ConcentratorCaptureSource()
        source._running = True
        source._wrapper = mock.Mock()
        entered, release = asyncio.Event(), asyncio.Event()

        async def start():
            entered.set()
            await release.wait()
            source._running = True

        with mock.patch.object(source, "start", side_effect=start):
            restart = asyncio.create_task(source.restart_pipeline())
            await asyncio.wait_for(entered.wait(), 1)
            stop = asyncio.create_task(source.stop())
            await asyncio.sleep(0)
            self.assertFalse(stop.done())
            release.set()
            await asyncio.gather(restart, stop)
        self.assertFalse(source._running)
        self.assertFalse(source._restarting)

    async def test_cancelled_restart_clears_pause_and_stops_hal(self):
        source = ConcentratorCaptureSource()
        source._running = True
        source._wrapper = mock.Mock()
        entered = asyncio.Event()

        async def start():
            entered.set()
            await asyncio.Event().wait()

        with mock.patch.object(source, "start", side_effect=start):
            restart = asyncio.create_task(source.restart_pipeline())
            await asyncio.wait_for(entered.wait(), 1)
            restart.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await restart
        self.assertFalse(source._running)
        self.assertFalse(source._restarting)
        self.assertEqual(source._wrapper.stop.call_count, 2)
