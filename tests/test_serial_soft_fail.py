"""Soft-fail + coordinator continue-on-fail for serial capture (Wave F)."""

from __future__ import annotations

import asyncio
import unittest
from typing import AsyncIterator, Optional
from unittest.mock import MagicMock, patch

from src.capture.base import CaptureSource
from src.capture.capture_coordinator import CaptureCoordinator
from src.capture.serial_source import SerialCaptureSource
from src.models.packet import RawCapture


class _StubSource(CaptureSource):
    """Minimal capture source for coordinator tests."""

    def __init__(self, name: str, fail: Optional[BaseException] = None):
        self._name = name
        self._fail = fail
        self.started = False
        self._running = False

    @property
    def name(self) -> str:
        return self._name

    @property
    def is_running(self) -> bool:
        return self._running

    async def start(self) -> None:
        if self._fail is not None:
            raise self._fail
        self.started = True
        self._running = True

    async def stop(self) -> None:
        self._running = False

    async def packets(self) -> AsyncIterator[RawCapture]:
        while self._running:
            await asyncio.sleep(0.05)
        if False:  # pragma: no cover
            yield  # async-generator shape for CaptureCoordinator


class SerialSoftFailTest(unittest.IsolatedAsyncioTestCase):
    async def test_busy_port_does_not_raise(self):
        source = SerialCaptureSource(port="/dev/ttyUSB-busy")

        with patch.object(
            source,
            "_open_interface",
            side_effect=OSError("Device or resource busy"),
        ):
            await source.start()

        self.assertTrue(source.is_running)
        self.assertFalse(source.connected)
        self.assertIsNotNone(source._reconnect_task)
        await source.stop()
        self.assertFalse(source.is_running)

    async def test_missing_meshtastic_still_raises(self):
        source = SerialCaptureSource(port="/dev/ttyUSB0")

        with patch.object(
            source,
            "_open_interface",
            side_effect=ImportError("meshtastic"),
        ):
            with self.assertRaises(ImportError):
                await source.start()

        self.assertFalse(source.is_running)


class CaptureCoordinatorContinueOnFailTest(unittest.IsolatedAsyncioTestCase):
    async def test_second_source_starts_after_first_soft_fail(self):
        soft = SerialCaptureSource(port="/dev/ttyUSB-busy")
        ok = _StubSource("concentrator")
        coordinator = CaptureCoordinator()
        coordinator.add_source(soft)
        coordinator.add_source(ok)

        with patch.object(
            soft,
            "_open_interface",
            side_effect=OSError("Device or resource busy"),
        ):
            await coordinator.start()

        self.assertTrue(ok.started)
        self.assertEqual(coordinator.source_count, 2)
        await coordinator.stop()

    async def test_hard_exception_from_one_source_does_not_abort_others(self):
        bad = _StubSource("serial", fail=RuntimeError("port locked"))
        ok = _StubSource("concentrator")
        coordinator = CaptureCoordinator()
        coordinator.add_source(bad)
        coordinator.add_source(ok)

        await coordinator.start()

        self.assertFalse(bad.started)
        self.assertTrue(ok.started)
        await coordinator.stop()

    async def test_import_error_still_aborts_coordinator(self):
        bad = _StubSource("serial", fail=ImportError("meshtastic"))
        ok = _StubSource("concentrator")
        coordinator = CaptureCoordinator()
        coordinator.add_source(bad)
        coordinator.add_source(ok)

        with self.assertRaises(ImportError):
            await coordinator.start()

        self.assertFalse(ok.started)


class SerialLiveDropReconnectTest(unittest.IsolatedAsyncioTestCase):
    """Set Preset / unplug must not leave a dead SerialInterface looking connected."""

    async def test_connection_lost_clears_connected_and_schedules_reconnect(self):
        source = SerialCaptureSource(port="/dev/ttyUSB0")
        source._running = True
        source._reconnect.bind_loop(asyncio.get_running_loop())
        iface = MagicMock()
        source._interface = iface

        source._on_connection_lost(interface=iface)

        self.assertFalse(source.connected)
        iface.close.assert_called_once()
        snap = source.link_status()
        self.assertTrue(snap["reconnecting"])
        self.assertEqual(snap["link_phase"], "reconnecting")
        self.assertIsNotNone(source._reconnect_task)
        await source.stop()

    async def test_foreign_interface_is_ignored(self):
        source = SerialCaptureSource(port="/dev/ttyUSB0")
        source._running = True
        source._reconnect.bind_loop(asyncio.get_running_loop())
        iface = MagicMock()
        source._interface = iface

        source._on_connection_lost(interface=object())

        self.assertTrue(source.connected)
        iface.close.assert_not_called()
        self.assertIsNone(source._reconnect_task)
        await source.stop()

    async def test_set_modem_preset_success_drops_link_for_reconnect(self):
        source = SerialCaptureSource(port="/dev/ttyUSB0")
        source._running = True
        source._reconnect.bind_loop(asyncio.get_running_loop())
        iface = MagicMock()
        source._interface = iface
        writer = MagicMock()
        writer.set_modem_preset.return_value = {
            "success": True,
            "modem_preset": "MEDIUM_FAST",
        }

        with patch.object(source, "_config_writer", return_value=writer):
            result = source.set_modem_preset("MEDIUM_FAST")

        self.assertTrue(result["success"])
        self.assertFalse(source.connected)
        iface.close.assert_called_once()
        snap = source.link_status()
        self.assertTrue(snap["reconnecting"])
        self.assertEqual(snap["link_phase"], "rebooting")
        self.assertGreaterEqual(snap["retry_in_s"], 10)
        self.assertIsNotNone(source._reconnect_task)
        await source.stop()

    async def test_failed_preset_write_keeps_link(self):
        source = SerialCaptureSource(port="/dev/ttyUSB0")
        source._running = True
        source._reconnect.bind_loop(asyncio.get_running_loop())
        iface = MagicMock()
        source._interface = iface
        writer = MagicMock()
        writer.set_modem_preset.return_value = {
            "success": False,
            "error": "Unknown modem preset",
        }

        with patch.object(source, "_config_writer", return_value=writer):
            result = source.set_modem_preset("NOPE")

        self.assertFalse(result["success"])
        self.assertTrue(source.connected)
        iface.close.assert_not_called()
        self.assertIsNone(source._reconnect_task)
        await source.stop()


if __name__ == "__main__":
    unittest.main()
