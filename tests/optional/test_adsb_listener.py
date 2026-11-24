"""Tests for the ADS-B listener's lifecycle + aircraft snapshot handling.

FastAPI-free: plugins/apps/adsb/backend/listener.py imports only stdlib +
src/audio/sdr_registry.py, so it runs directly on the Mac. The dump1090
subprocess is faked with a real asyncio.StreamReader for stderr; its
/data.json webserver is faked by monkeypatching
AdsbListener._fetch_aircraft_sync directly (no real HTTP server spawned).
Mirrors plugins/apps/rtl433/backend/tests/test_listener.py.
"""

from __future__ import annotations

import asyncio
import unittest
from unittest import mock

from apps.adsb.backend import listener as adsb_listener
from apps.adsb.backend.listener import AdsbListener
from src.audio import sdr_registry


def _reader(*lines: bytes, eof: bool = True) -> asyncio.StreamReader:
    r = asyncio.StreamReader()
    for ln in lines:
        r.feed_data(ln)
    if eof:
        r.feed_eof()
    return r


class _FakeProc:
    def __init__(self, stderr: asyncio.StreamReader):
        self.stdout = None
        self.stderr = stderr
        self.returncode = None
        self.pid = 424242

    async def wait(self):
        self.returncode = 0
        return 0


_RAW_AIRCRAFT = [
    {"hex": "4b1234", "flight": "KLM123 ", "squawk": "1000", "altitude": 35000,
     "speed": 450, "track": 90, "validtrack": True, "vert_rate": 0,
     "lat": 52.3, "lon": 4.9, "validposition": True, "messages": 10, "seen": 2},
    {"hex": "4b5678", "flight": "", "squawk": "", "altitude": None,
     "speed": None, "validtrack": False, "validposition": False,
     "messages": 1, "seen": 30},
]


class TestAdsbListener(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        sdr_registry._owner = None
        self.patchers = [
            mock.patch("shutil.which", return_value="/usr/local/bin/dump1090"),
            mock.patch("os.killpg", create=True),
            mock.patch("os.getpgid", return_value=1, create=True),
        ]
        for p in self.patchers:
            p.start()

    def tearDown(self) -> None:
        for p in self.patchers:
            p.stop()
        sdr_registry._owner = None

    async def _start(self, metric: bool = True) -> AdsbListener:
        proc = _FakeProc(_reader())
        lis = AdsbListener()
        with mock.patch("asyncio.create_subprocess_exec",
                        new=mock.AsyncMock(return_value=proc)):
            with mock.patch.object(adsb_listener, "_START_CHECK_SECS", 0.02):
                await lis.start(metric=metric)
        self.assertTrue(lis.running)
        return lis

    async def test_poll_loop_parses_snapshot_and_sorts_by_seen(self) -> None:
        lis = await self._start()
        with mock.patch.object(lis, "_fetch_aircraft_sync", return_value=_RAW_AIRCRAFT):
            with mock.patch.object(adsb_listener, "_POLL_SECS", 0.01):
                lis._poll_task.cancel()
                loop = asyncio.get_running_loop()
                lis._poll_task = loop.create_task(lis._poll_loop())
                for _ in range(20):
                    await asyncio.sleep(0.01)
                    if lis.aircraft:
                        break
        # Assert before stop() -- stop() deliberately clears self.aircraft.
        self.assertEqual(len(lis.aircraft), 2)
        # Most recently heard (lowest "seen") first.
        self.assertEqual(lis.aircraft[0]["hex"], "4b1234")
        self.assertEqual(lis.aircraft[0]["flight"], "KLM123")
        self.assertEqual(lis.aircraft[0]["lat"], 52.3)
        self.assertEqual(lis.aircraft[1]["hex"], "4b5678")
        self.assertIsNone(lis.aircraft[1]["lat"])
        await lis.stop()

    async def test_failed_poll_keeps_previous_snapshot(self) -> None:
        lis = await self._start()
        with mock.patch.object(lis, "_fetch_aircraft_sync", return_value=_RAW_AIRCRAFT):
            with mock.patch.object(adsb_listener, "_POLL_SECS", 0.01):
                lis._poll_task.cancel()
                loop = asyncio.get_running_loop()
                lis._poll_task = loop.create_task(lis._poll_loop())
                for _ in range(20):
                    await asyncio.sleep(0.01)
                    if lis.aircraft:
                        break
        self.assertEqual(len(lis.aircraft), 2)
        with mock.patch.object(lis, "_fetch_aircraft_sync", return_value=None):
            with mock.patch.object(adsb_listener, "_POLL_SECS", 0.01):
                lis._poll_task.cancel()
                loop = asyncio.get_running_loop()
                lis._poll_task = loop.create_task(lis._poll_loop())
                await asyncio.sleep(0.05)
        self.assertEqual(len(lis.aircraft), 2)  # unchanged, not blanked
        await lis.stop()

    async def test_status_shape_and_metric_flag(self) -> None:
        lis = await self._start(metric=False)
        st = lis.status()
        self.assertEqual(
            set(st),
            {"running", "aircraft_count", "aircraft", "last_error",
             "metric", "dongle_owner"},
        )
        self.assertFalse(st["metric"])
        await lis.stop()

    async def test_stop_clears_aircraft(self) -> None:
        lis = await self._start()
        lis.aircraft = list(_RAW_AIRCRAFT)
        await lis.stop()
        self.assertEqual(lis.aircraft, [])
        self.assertFalse(lis.running)

    async def test_missing_binary_raises(self) -> None:
        with mock.patch("shutil.which", return_value=None):
            with self.assertRaises(RuntimeError):
                await AdsbListener().start()

    async def test_dongle_owned_by_other_listener_raises(self) -> None:
        sdr_registry.claim("rtl433")
        with self.assertRaises(RuntimeError):
            await AdsbListener().start()


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
