"""Tests for the DAB+ listener's lifecycle + mux.json polling.

FastAPI-free: plugins/apps/dab/backend/listener.py imports only stdlib +
src/audio/sdr_registry.py, so it runs directly on the Mac. The welle-cli
subprocess is faked with a real asyncio.StreamReader for stderr; its
/mux.json webserver is faked by monkeypatching
DabListener._fetch_mux_json_sync directly (no real HTTP server spawned).
Mirrors plugins/apps/adsb/backend/tests/test_listener.py.
"""

from __future__ import annotations

import asyncio
import unittest
from unittest import mock

from apps.dab.backend import listener as dab_listener
from apps.dab.backend.listener import DabListener
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


_MUX_JSON = {
    "ensemble": {"label": {"label": "Commercial "}},
    "demodulator": {"snr": 8.5},
    "services": [
        {
            "sid": "0x8201", "label": {"label": "NPO 3FM "},
            "dls": {"label": "Now playing: Foo"}, "ptystring": "Pop Music",
            "url_mp3": "/mp3/0x8201",
        },
        # Data-only service (e.g. TPEG): no url_mp3 -- must be skipped.
        {"sid": "0x8202", "label": {"label": "TPEG"}},
    ],
}


class TestDabListener(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        sdr_registry._owner = None
        self.patchers = [
            mock.patch("shutil.which", return_value="/usr/local/bin/welle-cli"),
            mock.patch("os.killpg", create=True),
            mock.patch("os.getpgid", return_value=1, create=True),
        ]
        for p in self.patchers:
            p.start()

    def tearDown(self) -> None:
        for p in self.patchers:
            p.stop()
        sdr_registry._owner = None

    async def _tune(self, channel: str = "12C") -> DabListener:
        proc = _FakeProc(_reader())
        lis = DabListener()
        with mock.patch("asyncio.create_subprocess_exec",
                        new=mock.AsyncMock(return_value=proc)):
            with mock.patch.object(dab_listener, "_START_CHECK_SECS", 0.02):
                await lis.tune(channel)
        self.assertTrue(lis.running)
        return lis

    async def test_tune_rejects_invalid_channel(self) -> None:
        with self.assertRaises(ValueError):
            await DabListener().tune("not a channel!")

    async def test_missing_binary_raises(self) -> None:
        with mock.patch("shutil.which", return_value=None):
            with self.assertRaises(RuntimeError):
                await DabListener().tune("12C")

    async def test_dongle_owned_by_other_listener_raises(self) -> None:
        sdr_registry.claim("rtl433")
        with self.assertRaises(RuntimeError):
            await DabListener().tune("12C")

    async def test_status_shape_after_tune(self) -> None:
        lis = await self._tune()
        st = lis.status()
        self.assertEqual(
            set(st),
            {"running", "channel", "ensemble_label", "snr", "services",
             "last_error", "dongle_owner"},
        )
        self.assertEqual(st["channel"], "12C")
        self.assertEqual(st["dongle_owner"], "dab")
        await lis.stop()

    async def test_mux_poll_loop_parses_ensemble_and_skips_data_only(self) -> None:
        lis = await self._tune()
        with mock.patch.object(lis, "_fetch_mux_json_sync", return_value=_MUX_JSON):
            with mock.patch.object(dab_listener, "_MUX_POLL_SECS", 0.01):
                lis._poll_task.cancel()
                loop = asyncio.get_running_loop()
                lis._poll_task = loop.create_task(lis._mux_poll_loop())
                for _ in range(20):
                    await asyncio.sleep(0.01)
                    if lis.services:
                        break
        self.assertEqual(lis.ensemble_label, "Commercial")
        self.assertEqual(lis.snr, 8.5)
        # Only the audio-capable service (has url_mp3) is kept.
        self.assertEqual(len(lis.services), 1)
        self.assertEqual(lis.services[0]["sid"], "0x8201")
        self.assertEqual(lis.services[0]["label"], "NPO 3FM")
        self.assertEqual(lis.services[0]["dls"], "Now playing: Foo")
        await lis.stop()

    async def test_failed_poll_keeps_previous_snapshot(self) -> None:
        lis = await self._tune()
        with mock.patch.object(lis, "_fetch_mux_json_sync", return_value=_MUX_JSON):
            with mock.patch.object(dab_listener, "_MUX_POLL_SECS", 0.01):
                lis._poll_task.cancel()
                loop = asyncio.get_running_loop()
                lis._poll_task = loop.create_task(lis._mux_poll_loop())
                for _ in range(20):
                    await asyncio.sleep(0.01)
                    if lis.services:
                        break
        self.assertEqual(len(lis.services), 1)
        with mock.patch.object(lis, "_fetch_mux_json_sync", return_value=None):
            with mock.patch.object(dab_listener, "_MUX_POLL_SECS", 0.01):
                lis._poll_task.cancel()
                loop = asyncio.get_running_loop()
                lis._poll_task = loop.create_task(lis._mux_poll_loop())
                await asyncio.sleep(0.05)
        self.assertEqual(len(lis.services), 1)  # unchanged, not blanked
        await lis.stop()

    async def test_stop_clears_state(self) -> None:
        lis = await self._tune()
        lis.ensemble_label = "Commercial"
        lis.services = [{"sid": "0x8201", "label": "NPO 3FM"}]
        await lis.stop()
        self.assertFalse(lis.running)
        self.assertEqual(lis.channel, "")
        self.assertEqual(lis.ensemble_label, "")
        self.assertEqual(lis.services, [])

    async def test_retune_releases_and_reclaims_dongle(self) -> None:
        lis = await self._tune("12C")
        proc2 = _FakeProc(_reader())
        with mock.patch("asyncio.create_subprocess_exec",
                        new=mock.AsyncMock(return_value=proc2)):
            with mock.patch.object(dab_listener, "_START_CHECK_SECS", 0.02):
                with mock.patch.object(dab_listener, "_DEVICE_SETTLE_SECS", 0.01):
                    await lis.tune("9C")
        self.assertEqual(lis.channel, "9C")
        self.assertEqual(sdr_registry.current_owner(), "dab")
        await lis.stop()
        self.assertIsNone(sdr_registry.current_owner())


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
