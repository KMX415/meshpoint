"""Tests for in-process concentrator pipeline restart."""

from __future__ import annotations

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
