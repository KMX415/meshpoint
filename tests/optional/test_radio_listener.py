"""Tests for the Radio (RtlListener) lifecycle, status shape, and the
subscriber fan-out -- Radio never had unit tests at the core level before
this extraction.

FastAPI-free: plugins/apps/radio/backend/listener.py imports only stdlib +
src/audio/sdr_registry.py, so it runs directly on the Mac. The
rtl_fm|ffmpeg pipeline is faked with a real asyncio.StreamReader for
stderr; RDS/level-meter parsing is tested via the pure helper methods
directly rather than a real redsea/ffmpeg subprocess. Mirrors
plugins/apps/dab/backend/tests/test_listener.py.
"""

from __future__ import annotations

import asyncio
import unittest
from unittest import mock

from apps.radio.backend import listener as radio_listener
from apps.radio.backend.listener import RtlListener
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
        # No feed_eof(): an immediately-EOF stdout reads as "the process
        # died" to _read_loop() (which shares this stdout as the audio
        # fan-out source, unlike DAB+'s per-client stream proxy), release
        # the dongle, and fail every retry attempt. Leaving it open with
        # no data represents "alive, just not producing audio yet" --
        # reads on it simply stay pending, which every test here is fine
        # with since none of them assert on actual fan-out bytes.
        self.stdout = asyncio.StreamReader()
        self.stderr = stderr
        self.returncode = None
        self.pid = 424242

    async def wait(self):
        self.returncode = 0
        return 0


class TestRtlListener(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        sdr_registry._owner = None
        self.patchers = [
            mock.patch("shutil.which", return_value="/usr/local/bin/rtl_fm"),
            mock.patch("os.killpg", create=True),
            mock.patch("os.getpgid", return_value=1, create=True),
        ]
        for p in self.patchers:
            p.start()

    def tearDown(self) -> None:
        for p in self.patchers:
            p.stop()
        sdr_registry._owner = None

    async def _tune(self, **kw) -> RtlListener:
        proc = _FakeProc(_reader())
        lis = RtlListener(region="US")
        kw.setdefault("frequency_hz", 98_000_000)
        kw.setdefault("mode", "wfm")
        with mock.patch("asyncio.create_subprocess_exec",
                        new=mock.AsyncMock(return_value=proc)):
            with mock.patch.object(radio_listener, "_START_CHECK_SECS", 0.02):
                await lis.tune(**kw)
        self.assertTrue(lis.running)
        return lis

    async def test_tune_rejects_unknown_mode(self) -> None:
        with self.assertRaises(ValueError):
            await RtlListener(region="US").tune(98_000_000, mode="wideband")

    async def test_tune_rejects_out_of_range_frequency(self) -> None:
        with self.assertRaises(ValueError):
            await RtlListener(region="US").tune(1, mode="nfm")
        with self.assertRaises(ValueError):
            await RtlListener(region="US").tune(radio_listener.MAX_FREQ_HZ + 1, mode="nfm")

    async def test_missing_rtl_fm_raises(self) -> None:
        with mock.patch("shutil.which", side_effect=lambda b: None if b == "rtl_fm" else "/x"):
            with self.assertRaises(RuntimeError):
                await RtlListener(region="US").tune(98_000_000, mode="wfm")

    async def test_missing_ffmpeg_raises(self) -> None:
        with mock.patch("shutil.which", side_effect=lambda b: None if b == "ffmpeg" else "/x"):
            with self.assertRaises(RuntimeError):
                await RtlListener(region="US").tune(98_000_000, mode="wfm")

    async def test_dongle_owned_by_other_listener_raises(self) -> None:
        sdr_registry.claim("p2000")
        with self.assertRaises(RuntimeError):
            await RtlListener(region="US").tune(98_000_000, mode="wfm")

    async def test_status_shape_and_defaults(self) -> None:
        lis = await self._tune(station_label="Radio 10")
        st = lis.status()
        self.assertEqual(
            set(st),
            {
                "running", "frequency_hz", "frequency_mhz", "mode",
                "station_label", "squelch", "gain", "volume", "audio_level",
                "rds_ps", "rds_rt", "rds_pty", "rds_bler", "listeners",
                "last_error", "dongle_owner", "region", "deemphasis_us",
            },
        )
        self.assertEqual(st["frequency_mhz"], 98.0)
        self.assertEqual(st["station_label"], "Radio 10")
        self.assertEqual(st["dongle_owner"], "radio")
        await lis.stop()

    async def test_stop_clears_rds_state_and_label(self) -> None:
        lis = await self._tune(station_label="Radio 10")
        lis.rds_ps = "NPO 3FM"
        lis.rds_rt = "now playing something"
        lis.rds_bler = 2.0
        await lis.stop()
        self.assertFalse(lis.running)
        self.assertEqual(lis.station_label, "")
        self.assertEqual(lis.rds_ps, "")
        self.assertEqual(lis.rds_rt, "")
        self.assertEqual(lis.rds_bler, -1.0)
        self.assertIsNone(sdr_registry.current_owner())

    async def test_subscribe_unsubscribe_tracked_in_status(self) -> None:
        lis = await self._tune()
        q1 = lis.subscribe()
        q2 = lis.subscribe()
        self.assertEqual(lis.status()["listeners"], 2)
        lis.unsubscribe(q1)
        self.assertEqual(lis.status()["listeners"], 1)
        lis.unsubscribe(q2)
        self.assertEqual(lis.status()["listeners"], 0)
        await lis.stop()

    def test_update_level_maps_lufs_to_0_100(self) -> None:
        lis = RtlListener(region="US")
        lis._update_level(str(radio_listener._LUFS_FLOOR - 5))
        self.assertEqual(lis.audio_level, 0.0)
        lis._update_level(str(radio_listener._LUFS_CEIL + 5))
        self.assertEqual(lis.audio_level, 100.0)
        mid = (radio_listener._LUFS_FLOOR + radio_listener._LUFS_CEIL) / 2
        lis._update_level(str(mid))
        self.assertAlmostEqual(lis.audio_level, 50.0, delta=0.5)

    def test_update_level_ignores_garbage(self) -> None:
        lis = RtlListener(region="US")
        lis.audio_level = 42.0
        lis._update_level("not-a-number")
        self.assertEqual(lis.audio_level, 42.0)

    async def test_retune_releases_and_reclaims_dongle(self) -> None:
        lis = await self._tune(frequency_hz=98_000_000, mode="wfm")
        proc2 = _FakeProc(_reader())
        with mock.patch("asyncio.create_subprocess_exec",
                        new=mock.AsyncMock(return_value=proc2)):
            with mock.patch.object(radio_listener, "_START_CHECK_SECS", 0.02):
                with mock.patch.object(radio_listener, "_DEVICE_SETTLE_SECS", 0.01):
                    await lis.tune(92_300_000, mode="wfm")
        self.assertEqual(lis.frequency_hz, 92_300_000)
        self.assertEqual(sdr_registry.current_owner(), "radio")
        await lis.stop()
        self.assertIsNone(sdr_registry.current_owner())


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
