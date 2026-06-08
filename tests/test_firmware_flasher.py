"""USB companion firmware flasher (PR 14)."""

from __future__ import annotations

import asyncio
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from src.firmware.flasher import FlashJob, get_port_lock, run_flash_job
from src.firmware.upload_store import FirmwareUploadStore


def _run(coro):
    return asyncio.run(coro)


class _AsyncStdout:
    def __init__(self, lines: list[bytes]) -> None:
        self._lines = iter(lines)

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            return next(self._lines)
        except StopIteration:
            raise StopAsyncIteration from None


class TestRunFlashJob(unittest.TestCase):
    def _make_job(self, callback=None):
        cb = callback or AsyncMock()
        job = FlashJob(
            port="/dev/ttyUSB0",
            baud=460800,
            offset="0x10000",
            bin_path=Path("/tmp/test_fw.bin"),
            log_callback=cb,
        )
        return job, cb

    def test_success_returns_true(self):
        job, _cb = self._make_job()
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = _AsyncStdout([b"Writing at 0x10000...\n", b"Hash OK\n"])
        mock_proc.wait = AsyncMock()

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            result = _run(run_flash_job(job))
        self.assertTrue(result)

    def test_failure_returns_false(self):
        job, _cb = self._make_job()
        mock_proc = MagicMock()
        mock_proc.returncode = 2
        mock_proc.stdout = _AsyncStdout([b"Failed to connect\n"])
        mock_proc.wait = AsyncMock()

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            result = _run(run_flash_job(job))
        self.assertFalse(result)

    def test_missing_esptool_returns_false(self):
        job, _cb = self._make_job()
        with patch(
            "asyncio.create_subprocess_exec",
            side_effect=FileNotFoundError("esptool not found"),
        ):
            result = _run(run_flash_job(job))
        self.assertFalse(result)

    def test_log_callback_receives_stdout_lines(self):
        lines_received: list[str] = []

        async def capture(msg: str) -> None:
            lines_received.append(msg)

        job, _ = self._make_job(callback=capture)
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = _AsyncStdout([b"line one\n", b"line two\n"])
        mock_proc.wait = AsyncMock()

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            _run(run_flash_job(job))

        joined = "\n".join(lines_received)
        self.assertIn("line one", joined)
        self.assertIn("line two", joined)

    def test_port_lock_is_per_port(self):
        lock_a = get_port_lock("/dev/ttyUSB0")
        lock_b = get_port_lock("/dev/ttyACM0")
        lock_a2 = get_port_lock("/dev/ttyUSB0")
        self.assertIs(lock_a, lock_a2)
        self.assertIsNot(lock_a, lock_b)


class TestFirmwareUploadStore(unittest.TestCase):
    def test_store_and_pop(self):
        store = FirmwareUploadStore()
        path = Path("/tmp/fake.bin")
        upload_id = store.store(path, "fw.bin", 1024)
        record = store.pop(upload_id)
        self.assertIsNotNone(record)
        self.assertEqual(record.filename, "fw.bin")
        self.assertIsNone(store.pop(upload_id))


if __name__ == "__main__":
    unittest.main()
