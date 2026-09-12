"""Tests for the ACARS listener's JSON parsing + lifecycle.

FastAPI-free: src/audio/acars_listener.py imports only stdlib +
src/audio/sdr_registry.py, so it runs directly on the Mac. The acarsdec
subprocess is faked with real asyncio.StreamReader objects; no binary is
spawned.
"""

from __future__ import annotations

import asyncio
import json
import unittest
from unittest import mock

from apps.acars.backend import listener as acars_listener
from apps.acars.backend.listener import AcarsListener
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


_SAMPLE = [
    json.dumps({"timestamp": 1.0, "channel": 2, "freq": 131.725,
                "label": "H1", "tail": "PH-BVC", "flight": "KL0843",
                "text": "RTE 1 EHAM/VTBS"}).encode() + b"\n",
    b"not json at all\n",
    json.dumps([1, 2, 3]).encode() + b"\n",          # valid json, not a dict
    json.dumps({"label": "5Z", "tail": "D-AIGS", "text": "OK"}).encode() + b"\n",
    b"\n",                                            # blank line
]


class TestAcarsListener(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        sdr_registry._owner = None
        self.patchers = [
            mock.patch("shutil.which", return_value="/usr/local/bin/acarsdec"),
            mock.patch("os.killpg", create=True),
            mock.patch("os.getpgid", return_value=1, create=True),
        ]
        for p in self.patchers:
            p.start()

    def tearDown(self) -> None:
        for p in self.patchers:
            p.stop()
        sdr_registry._owner = None

    async def _run_with(self, *stdout_lines: bytes) -> AcarsListener:
        # stdout stays open (no EOF) so the fake process reads as "alive"
        # and the startup retry loop settles on the first check.
        proc = _FakeProc(_reader(*stdout_lines, eof=False), _reader())
        lis = AcarsListener(frequencies=["131.725"])
        with mock.patch("asyncio.create_subprocess_exec",
                        new=mock.AsyncMock(return_value=proc)):
            # shorten the retry-loop sleeps so the test isn't slow
            with mock.patch.object(acars_listener, "_START_CHECK_SECS", 0.02):
                await lis.start()
        for _ in range(50):          # let the read loop drain fed lines
            await asyncio.sleep(0)
        self.assertTrue(lis.running)
        await lis.stop()
        return lis

    async def test_parses_json_messages_and_skips_junk(self) -> None:
        lis = await self._run_with(*_SAMPLE)
        self.assertEqual(len(lis.messages), 2)
        first = lis.messages[0]
        self.assertEqual(first["tail"], "PH-BVC")
        self.assertEqual(first["flight"], "KL0843")
        self.assertIn("received_at", first)
        self.assertEqual(lis.messages[1]["tail"], "D-AIGS")

    async def test_ring_buffer_caps_at_200(self) -> None:
        lines = [json.dumps({"n": i, "text": "x"}).encode() + b"\n" for i in range(260)]
        lis = await self._run_with(*lines)
        self.assertEqual(len(lis.messages), 200)
        self.assertEqual(lis.messages[-1]["n"], 259)

    async def test_status_shape(self) -> None:
        lis = await self._run_with(*_SAMPLE)
        st = lis.status()
        self.assertEqual(
            set(st),
            {"running", "frequencies", "message_count", "messages",
             "last_error", "dongle_owner"},
        )
        self.assertEqual(st["frequencies"], ["131.725"])
        self.assertEqual(st["message_count"], 2)

    async def test_clear_empties_buffer(self) -> None:
        lis = await self._run_with(*_SAMPLE)
        lis.clear()
        self.assertEqual(len(lis.messages), 0)
        self.assertEqual(lis.status()["message_count"], 0)

    async def test_missing_binary_raises(self) -> None:
        with mock.patch("shutil.which", return_value=None):
            with self.assertRaises(RuntimeError):
                await AcarsListener(frequencies=["131.725"]).start()

    async def test_dongle_owned_by_other_listener_raises(self) -> None:
        sdr_registry.claim("adsb")
        with self.assertRaises(RuntimeError):
            await AcarsListener(frequencies=["131.725"]).start()

    async def test_config_overrides_are_used_in_the_command_line(self) -> None:
        proc = _FakeProc(_reader(eof=False), _reader())
        lis = AcarsListener(frequencies=["136.900"], gain="20", device="1")
        captured = {}

        async def _fake_exec(*args, **kwargs):
            captured["args"] = args
            return proc

        with mock.patch("asyncio.create_subprocess_exec", new=_fake_exec):
            with mock.patch.object(acars_listener, "_START_CHECK_SECS", 0.02):
                await lis.start()
        await lis.stop()

        self.assertEqual(captured["args"][captured["args"].index("-g") + 1], "20")
        self.assertEqual(
            captured["args"][captured["args"].index("--rtlsdr") + 1], "1",
        )
        self.assertEqual(captured["args"][-1], "136.900")
        self.assertEqual(lis.status()["frequencies"], ["136.900"])


class TestNormalizeFrequencies(unittest.TestCase):
    def test_missing_channels_do_not_select_a_region(self):
        self.assertEqual(acars_listener._normalize_frequencies(None), [])

    def test_invalid_channels_are_rejected(self):
        for value in ([], "131.725", [""], ["nan"], [117], [138], [131.5] * 9):
            with self.subTest(value=value), self.assertRaises(ValueError):
                acars_listener._normalize_frequencies(value)

    def test_explicit_channels_are_preserved(self):
        self.assertEqual(acars_listener._normalize_frequencies(["131.725", "131.800"]), ["131.725", "131.800"])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
