"""P25 integration checks independent of the pending decoder-setting review."""
import asyncio
import unittest
from unittest.mock import AsyncMock, patch

from apps.p25.backend.listener import P25Listener, PCMReceiver
from apps.p25.backend.settings import Settings
from src.audio import sdr_registry


class TestP25Lifecycle(unittest.IsolatedAsyncioTestCase):
    def tearDown(self):
        sdr_registry._owner = None

    async def test_creation_is_idle(self):
        with patch('asyncio.create_subprocess_exec') as spawn:
            self.assertFalse(P25Listener().status()['running'])
            spawn.assert_not_called()

    async def test_missing_dependencies_do_not_claim_hardware(self):
        with patch('shutil.which', return_value=None):
            with self.assertRaises(RuntimeError):
                await P25Listener().start(Settings(frequencies=[851.25]))
        self.assertIsNone(sdr_registry.current_owner())

    async def test_busy_receiver_is_not_interrupted(self):
        sdr_registry.claim('radio')
        with patch('shutil.which', return_value='tool'), patch('asyncio.create_subprocess_exec') as spawn:
            with self.assertRaises(RuntimeError):
                await P25Listener().start(Settings(frequencies=[851.25]))
            spawn.assert_not_called()
        self.assertEqual(sdr_registry.current_owner(), 'radio')

    async def test_failed_encoder_spawn_releases_resources(self):
        receiver = P25Listener()
        with patch('shutil.which', return_value='tool'), patch('asyncio.create_subprocess_exec', new=AsyncMock(side_effect=OSError('missing binary'))):
            with self.assertRaises(OSError):
                await receiver.start(Settings(frequencies=[851.25]))
        self.assertIsNone(receiver.directory)
        self.assertIsNone(receiver.transport)
        self.assertIsNone(sdr_registry.current_owner())

    async def test_audio_queue_is_bounded(self):
        queue = asyncio.Queue(maxsize=2)
        protocol = PCMReceiver(queue)
        for value in (b'aa' * 10, b'bb' * 10, b'cc' * 10):
            protocol.datagram_received(value, ('127.0.0.1', 1))
        self.assertEqual(queue.qsize(), 2)
        self.assertEqual(queue.get_nowait(), b'bb' * 10)

    async def test_stop_ends_stream(self):
        receiver = P25Listener()
        queue = receiver.subscribe()
        await receiver.stop()
        self.assertEqual(await queue.get(), b'')
