"""Tests for ``GpsdSource``: wire-protocol handling, reconnect, snapshot.

Mocks ``asyncio.open_connection`` with an in-memory ``StreamReader``-like
queue so the tests run without a real gpsd daemon.
"""

from __future__ import annotations

import asyncio
import json
import unittest
from unittest.mock import AsyncMock, patch

from src.hal.location.gpsd_source import GpsdSource


class _FakeReader:
    """Minimal ``readline``-only StreamReader for tests."""

    def __init__(self, lines: list[bytes]) -> None:
        self._lines = list(lines)
        self._closed = asyncio.Event()

    async def readline(self) -> bytes:
        if self._lines:
            return self._lines.pop(0)
        # Block indefinitely after the script runs out, simulating a
        # real connection that is still open.
        await self._closed.wait()
        return b""

    def close(self) -> None:
        self._closed.set()


class _FakeWriter:
    def __init__(self) -> None:
        self.written: list[bytes] = []
        self._closed = False

    def write(self, data: bytes) -> None:
        self.written.append(data)

    async def drain(self) -> None:
        return

    def close(self) -> None:
        self._closed = True

    async def wait_closed(self) -> None:
        return


def _line(payload: dict) -> bytes:
    return (json.dumps(payload) + "\n").encode("utf-8")


class TestGpsdSourceHandshake(unittest.IsolatedAsyncioTestCase):
    """Connection sends WATCH command before reading any data."""

    async def test_emits_watch_command_on_connect(self) -> None:
        reader = _FakeReader([])
        writer = _FakeWriter()
        with patch(
            "asyncio.open_connection",
            new=AsyncMock(return_value=(reader, writer)),
        ):
            source = GpsdSource()
            await source.start()
            await asyncio.sleep(0.05)  # let reader loop run

            self.assertGreaterEqual(len(writer.written), 1)
            self.assertIn(b"WATCH", writer.written[0])
            self.assertIn(b'"enable":true', writer.written[0])
            self.assertIn(b'"json":true', writer.written[0])

            await source.stop()


class TestGpsdSourceTpvHandling(unittest.IsolatedAsyncioTestCase):
    """TPV reports populate ``LocationFix`` and surface through ``get_status``."""

    async def test_3d_fix_publishes_position(self) -> None:
        tpv = {
            "class": "TPV",
            "mode": 3,
            "lat": 40.7128,
            "lon": -74.0060,
            "altMSL": 12.3,
            "speed": 0.05,
            "track": None,
            "time": "2026-05-30T16:37:01.000Z",
            "epx": 1.5,
            "epy": 1.6,
            "epv": 2.4,
            "hdop": 0.9,
        }
        reader = _FakeReader([_line(tpv)])
        writer = _FakeWriter()
        with patch(
            "asyncio.open_connection",
            new=AsyncMock(return_value=(reader, writer)),
        ):
            source = GpsdSource()
            await source.start()
            await asyncio.sleep(0.05)

            status = source.get_status()
            self.assertEqual(status.source, "gpsd")
            self.assertTrue(status.available)
            self.assertEqual(status.fix.mode, 3)
            self.assertAlmostEqual(status.fix.latitude, 40.7128)
            self.assertAlmostEqual(status.fix.longitude, -74.0060)
            self.assertAlmostEqual(status.fix.altitude_m, 12.3)
            self.assertEqual(status.fix.hdop, 0.9)

            reader.close()
            await source.stop()

    async def test_no_fix_below_min_quality_does_not_publish_position(self) -> None:
        # min_fix_quality=2 means we need a 2D fix or better. A mode=1
        # TPV must NOT promote to ``latest_fix`` with stale lat/lon.
        no_fix = {
            "class": "TPV",
            "mode": 1,
            "lat": None,
            "lon": None,
        }
        reader = _FakeReader([_line(no_fix)])
        writer = _FakeWriter()
        with patch(
            "asyncio.open_connection",
            new=AsyncMock(return_value=(reader, writer)),
        ):
            source = GpsdSource(min_fix_quality=2)
            await source.start()
            await asyncio.sleep(0.05)

            status = source.get_status()
            self.assertTrue(status.available)
            self.assertEqual(status.fix.mode, 1)
            self.assertIsNone(status.fix.latitude)
            self.assertIsNone(status.fix.longitude)
            self.assertEqual(status.fix.mode_label, "NO FIX")

            reader.close()
            await source.stop()

    async def test_alt_fallback_when_altMSL_missing(self) -> None:
        tpv = {
            "class": "TPV",
            "mode": 3,
            "lat": 40.0,
            "lon": -74.0,
            "alt": 10.0,
        }
        reader = _FakeReader([_line(tpv)])
        writer = _FakeWriter()
        with patch(
            "asyncio.open_connection",
            new=AsyncMock(return_value=(reader, writer)),
        ):
            source = GpsdSource()
            await source.start()
            await asyncio.sleep(0.05)

            status = source.get_status()
            self.assertEqual(status.fix.altitude_m, 10.0)

            reader.close()
            await source.stop()


class TestGpsdSourceSkyHandling(unittest.IsolatedAsyncioTestCase):
    """SKY reports populate the satellite list for the skyplot UI."""

    async def test_sky_message_publishes_satellites(self) -> None:
        sky = {
            "class": "SKY",
            "satellites": [
                {"PRN": 5, "az": 150.5, "el": 65.0, "ss": 42.0, "used": True, "gnssid": 0},
                {"PRN": 12, "az": 220.0, "el": 30.0, "ss": 35.0, "used": True, "gnssid": 0},
                {"PRN": 22, "az": 80.0, "el": 10.0, "ss": 18.0, "used": False, "gnssid": 6},
            ],
            "hdop": 1.1,
            "pdop": 1.5,
            "vdop": 1.0,
        }
        reader = _FakeReader([_line(sky)])
        writer = _FakeWriter()
        with patch(
            "asyncio.open_connection",
            new=AsyncMock(return_value=(reader, writer)),
        ):
            source = GpsdSource()
            await source.start()
            await asyncio.sleep(0.05)

            status = source.get_status()
            self.assertIsNotNone(status.satellites)
            self.assertEqual(status.satellites.in_view, 3)
            self.assertEqual(status.satellites.used, 2)

            sat_by_prn = {s.prn: s for s in status.satellites.satellites}
            self.assertEqual(sat_by_prn[5].gnss, "GPS")
            self.assertEqual(sat_by_prn[22].gnss, "GLONASS")
            self.assertAlmostEqual(sat_by_prn[5].azimuth, 150.5)
            self.assertAlmostEqual(sat_by_prn[5].elevation, 65.0)
            self.assertEqual(sat_by_prn[5].snr_dbhz, 42.0)
            self.assertTrue(sat_by_prn[5].used)
            self.assertFalse(sat_by_prn[22].used)

            reader.close()
            await source.stop()

    async def test_sky_dop_merges_into_existing_fix(self) -> None:
        # Some gpsd builds put DOP in SKY, not TPV. Verify we union
        # the values onto the prior LocationFix instead of dropping
        # them on the floor.
        tpv = {"class": "TPV", "mode": 3, "lat": 40.0, "lon": -74.0, "altMSL": 10.0}
        sky = {"class": "SKY", "satellites": [], "hdop": 1.2, "pdop": 1.7}
        reader = _FakeReader([_line(tpv), _line(sky)])
        writer = _FakeWriter()
        with patch(
            "asyncio.open_connection",
            new=AsyncMock(return_value=(reader, writer)),
        ):
            source = GpsdSource()
            await source.start()
            await asyncio.sleep(0.05)

            status = source.get_status()
            self.assertEqual(status.fix.hdop, 1.2)
            self.assertEqual(status.fix.pdop, 1.7)

            reader.close()
            await source.stop()


class TestGpsdSourceDevicesHandling(unittest.IsolatedAsyncioTestCase):
    """DEVICES reports populate device metadata for the UI chip."""

    async def test_ublox_8_recognized(self) -> None:
        devices = {
            "class": "DEVICES",
            "devices": [
                {
                    "path": "/dev/ttyACM0",
                    "driver": "u-blox",
                    "subtype": "PROTVER 18.00",
                }
            ],
        }
        reader = _FakeReader([_line(devices)])
        writer = _FakeWriter()
        with patch(
            "asyncio.open_connection",
            new=AsyncMock(return_value=(reader, writer)),
        ):
            source = GpsdSource()
            await source.start()
            await asyncio.sleep(0.05)

            status = source.get_status()
            self.assertIsNotNone(status.device)
            self.assertEqual(status.device.path, "/dev/ttyACM0")
            self.assertEqual(status.device.driver, "u-blox")
            self.assertEqual(status.device.model, "u-blox 8")

            reader.close()
            await source.stop()

    async def test_ublox_7_recognized(self) -> None:
        devices = {
            "class": "DEVICES",
            "devices": [
                {
                    "path": "/dev/ttyACM0",
                    "driver": "u-blox",
                    "subtype": "PROTVER 14.00",
                }
            ],
        }
        reader = _FakeReader([_line(devices)])
        writer = _FakeWriter()
        with patch(
            "asyncio.open_connection",
            new=AsyncMock(return_value=(reader, writer)),
        ):
            source = GpsdSource()
            await source.start()
            await asyncio.sleep(0.05)

            status = source.get_status()
            self.assertEqual(status.device.model, "u-blox 7")

            reader.close()
            await source.stop()


class TestGpsdSourceLifecycle(unittest.IsolatedAsyncioTestCase):
    """Start/stop semantics are idempotent and survive disconnect."""

    async def test_disconnect_marks_unavailable(self) -> None:
        # Empty reader -> readline returns b"" immediately -> session exits.
        # Reader loop will then enter backoff sleep.
        async def open_conn(*args, **kwargs):
            r = asyncio.StreamReader()
            r.feed_eof()
            w = _FakeWriter()
            return r, w

        with patch("asyncio.open_connection", side_effect=open_conn):
            source = GpsdSource()
            await source.start()
            # Give the reader loop time to connect, hit EOF, and disconnect.
            await asyncio.sleep(0.1)

            status = source.get_status()
            self.assertFalse(status.available)
            self.assertEqual(status.source, "gpsd")
            self.assertIsNone(status.fix)

            await source.stop()

    async def test_double_start_is_idempotent(self) -> None:
        reader = _FakeReader([])
        writer = _FakeWriter()
        open_mock = AsyncMock(return_value=(reader, writer))
        with patch("asyncio.open_connection", new=open_mock):
            source = GpsdSource()
            await source.start()
            await source.start()  # must not spawn a second reader task
            await asyncio.sleep(0.05)
            self.assertEqual(open_mock.await_count, 1)

            reader.close()
            await source.stop()

    async def test_stop_without_start_is_safe(self) -> None:
        source = GpsdSource()
        await source.stop()  # no exception

    async def test_unreachable_gpsd_marks_unavailable_with_error(self) -> None:
        with patch(
            "asyncio.open_connection",
            new=AsyncMock(
                side_effect=ConnectionRefusedError("Connection refused"),
            ),
        ):
            source = GpsdSource()
            await source.start()
            await asyncio.sleep(0.05)

            status = source.get_status()
            self.assertFalse(status.available)
            self.assertIsNotNone(status.error)
            self.assertIn("ConnectionRefusedError", status.error)

            await source.stop()


class TestGpsdSourceMessageRobustness(unittest.IsolatedAsyncioTestCase):
    """Malformed JSON and unknown classes don't crash the reader loop."""

    async def test_garbage_line_is_skipped(self) -> None:
        tpv = {"class": "TPV", "mode": 3, "lat": 40.0, "lon": -74.0, "altMSL": 5.0}
        reader = _FakeReader([
            b"not valid json\n",
            _line({"class": "VERSION", "release": "3.22"}),
            _line(tpv),
        ])
        writer = _FakeWriter()
        with patch(
            "asyncio.open_connection",
            new=AsyncMock(return_value=(reader, writer)),
        ):
            source = GpsdSource()
            await source.start()
            await asyncio.sleep(0.05)

            status = source.get_status()
            # Should still recover and parse the valid TPV after the garbage
            self.assertTrue(status.available)
            self.assertEqual(status.fix.mode, 3)

            reader.close()
            await source.stop()


if __name__ == "__main__":
    unittest.main()
