"""Tests for the P2000 listener's FLEX parsing + lifecycle.

FastAPI-free: plugins/apps/p2000/backend/listener.py imports only stdlib +
src/audio/sdr_registry.py, so it runs directly on the Mac. The
rtl_fm|multimon-ng pipeline is faked with real asyncio.StreamReader
objects; no binary is spawned. Mirrors plugins/apps/rtl433/backend/tests/
test_listener.py.
"""

from __future__ import annotations

import asyncio
import unittest
from unittest import mock

from apps.p2000.backend import listener as p2000_listener
from apps.p2000.backend.listener import P2000Listener
from src.audio import sdr_registry


def _reader(*lines: bytes, eof: bool = True) -> asyncio.StreamReader:
    r = asyncio.StreamReader()
    for ln in lines:
        r.feed_data(ln)
    if eof:
        r.feed_eof()
    return r


class _FakeProc:
    def __init__(self, stdout: asyncio.StreamReader, stderr: asyncio.StreamReader):
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = None
        self.pid = 424242

    async def wait(self):
        self.returncode = 0
        return 0


# Real captured P2000 FLEX line shape (see listener.py's docstring).
_FLEX_LINE = (
    b"FLEX|2026-07-13 18:51:53|1600/2/K/A|13.006|"
    b"002029582 000120161 000120999|ALN|"
    b"A1 13161 Heesterveld 1102 Amsterdam 67412\n"
)
_SAMPLE = [
    _FLEX_LINE,
    b"not a decoded line at all\n",
    b"FLEX|garbled|not-matching-the-real-format\n",  # recognized prefix, bad fields
    b"\n",  # blank line
]


class TestP2000Listener(unittest.IsolatedAsyncioTestCase):
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

    async def _run_with(self, *stdout_lines: bytes) -> P2000Listener:
        # stdout stays open (no EOF) so the fake process reads as "alive"
        # and the startup retry loop settles on the first check.
        proc = _FakeProc(_reader(*stdout_lines, eof=False), _reader())
        lis = P2000Listener()
        with mock.patch("asyncio.create_subprocess_exec",
                        new=mock.AsyncMock(return_value=proc)):
            with mock.patch.object(p2000_listener, "_START_CHECK_SECS", 0.02):
                await lis.start()
        for _ in range(50):          # let the read loop drain fed lines
            await asyncio.sleep(0)
        self.assertTrue(lis.running)
        await lis.stop()
        return lis

    async def test_parses_flex_and_skips_junk(self) -> None:
        lis = await self._run_with(*_SAMPLE)
        self.assertEqual(len(lis.messages), 2)  # real FLEX line + the garbled-but-prefixed one
        first = lis.messages[0]
        self.assertEqual(first["protocol"], "FLEX")
        self.assertEqual(first["capcode"], "002029582")
        self.assertEqual(first["message"], "A1 13161 Heesterveld 1102 Amsterdam 67412")
        self.assertIn("received_at", first)
        self.assertEqual(lis.messages[1]["protocol"], "unknown")

    async def test_ring_buffer_caps_at_200(self) -> None:
        lines = [_FLEX_LINE for _ in range(260)]
        lis = await self._run_with(*lines)
        self.assertEqual(len(lis.messages), 200)

    async def test_status_shape(self) -> None:
        lis = await self._run_with(*_SAMPLE)
        st = lis.status()
        self.assertEqual(
            set(st),
            {"kind", "running", "frequency_hz", "frequency_mhz",
             "message_count", "messages", "last_error", "dongle_owner"},
        )
        self.assertEqual(st["kind"], "p2000")
        self.assertEqual(st["frequency_hz"], 169_650_000)
        self.assertEqual(st["message_count"], 2)

    async def test_clear_empties_buffer(self) -> None:
        lis = await self._run_with(*_SAMPLE)
        lis.clear()
        self.assertEqual(len(lis.messages), 0)
        self.assertEqual(lis.status()["message_count"], 0)

    async def test_missing_rtl_fm_raises(self) -> None:
        with mock.patch("shutil.which", return_value=None):
            with self.assertRaises(RuntimeError):
                await P2000Listener().start()

    async def test_missing_multimon_ng_raises(self) -> None:
        def _which(name):
            return "/usr/local/bin/rtl_fm" if name == "rtl_fm" else None
        with mock.patch("shutil.which", side_effect=_which):
            with self.assertRaises(RuntimeError):
                await P2000Listener().start()

    async def test_dongle_owned_by_other_listener_raises(self) -> None:
        sdr_registry.claim("pagers")
        with self.assertRaises(RuntimeError):
            await P2000Listener().start()


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
