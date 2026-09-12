"""Tests for the POCSAG listener's parsing + lifecycle.

FastAPI-free: plugins/apps/pocsag/backend/listener.py imports only stdlib +
src/audio/sdr_registry.py, so it runs directly on the Mac. The
rtl_fm|multimon-ng pipeline is faked with real asyncio.StreamReader
objects; no binary is spawned. Mirrors plugins/apps/p2000/backend/tests/
test_listener.py.
"""

from __future__ import annotations

import asyncio
import unittest
from unittest import mock

from apps.pocsag.backend import listener as pocsag_listener
from apps.pocsag.backend.listener import PocsagListener
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


# multimon-ng pads alpha messages with literal "<NUL>" tokens -- confirmed
# on real captured output (see listener.py's _TRAILING_NUL_RE comment).
_ALPHA_LINE = b"POCSAG1200: Address: 1234567  Function: 3  Alpha:   Test message<NUL><NUL>\n"
_NUMERIC_LINE = b"POCSAG512: Address: 7654321  Function: 0  Numeric:  0123456789\n"
_SAMPLE = [
    _ALPHA_LINE,
    _NUMERIC_LINE,
    b"not a decoded line at all\n",
    b"POCSAG9999: garbled, not matching the real field layout\n",  # recognized prefix, bad fields
    b"\n",  # blank line
]


class TestPocsagListener(unittest.IsolatedAsyncioTestCase):
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

    async def _run_with(self, *stdout_lines: bytes) -> PocsagListener:
        # stdout stays open (no EOF) so the fake process reads as "alive"
        # and the startup retry loop settles on the first check.
        proc = _FakeProc(_reader(*stdout_lines, eof=False), _reader())
        lis = PocsagListener(frequency_mhz=439.9875)
        with mock.patch("asyncio.create_subprocess_exec",
                        new=mock.AsyncMock(return_value=proc)):
            with mock.patch.object(pocsag_listener, "_START_CHECK_SECS", 0.02):
                await lis.start()
        for _ in range(50):          # let the read loop drain fed lines
            await asyncio.sleep(0)
        self.assertTrue(lis.running)
        await lis.stop()
        return lis

    async def test_parses_pocsag_and_skips_junk(self) -> None:
        lis = await self._run_with(*_SAMPLE)
        self.assertEqual(len(lis.messages), 3)  # alpha + numeric + the garbled-but-prefixed one
        alpha = lis.messages[0]
        self.assertEqual(alpha["protocol"], "POCSAG1200")
        self.assertEqual(alpha["capcode"], "1234567")
        self.assertEqual(alpha["message"], "Test message")  # <NUL> padding stripped
        self.assertIn("received_at", alpha)
        numeric = lis.messages[1]
        self.assertEqual(numeric["protocol"], "POCSAG512")
        self.assertEqual(numeric["capcode"], "7654321")
        self.assertEqual(lis.messages[2]["protocol"], "unknown")

    async def test_ring_buffer_caps_at_200(self) -> None:
        lines = [_ALPHA_LINE for _ in range(260)]
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
        self.assertEqual(st["kind"], "pocsag")
        self.assertEqual(st["frequency_hz"], 439_987_500)
        self.assertEqual(st["message_count"], 3)

    async def test_clear_empties_buffer(self) -> None:
        lis = await self._run_with(*_SAMPLE)
        lis.clear()
        self.assertEqual(len(lis.messages), 0)
        self.assertEqual(lis.status()["message_count"], 0)

    async def test_missing_rtl_fm_raises(self) -> None:
        with mock.patch("shutil.which", return_value=None):
            with self.assertRaises(RuntimeError):
                await PocsagListener(frequency_mhz=439.9875).start()

    async def test_missing_multimon_ng_raises(self) -> None:
        def _which(name):
            return "/usr/local/bin/rtl_fm" if name == "rtl_fm" else None
        with mock.patch("shutil.which", side_effect=_which):
            with self.assertRaises(RuntimeError):
                await PocsagListener(frequency_mhz=439.9875).start()

    async def test_dongle_owned_by_other_listener_raises(self) -> None:
        sdr_registry.claim("pagers")
        with self.assertRaises(RuntimeError):
            await PocsagListener(frequency_mhz=439.9875).start()


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
