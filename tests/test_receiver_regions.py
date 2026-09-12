"""Regional selection must not open a receiver on an implicit local channel."""
import unittest
from unittest.mock import patch

from apps.pagers.backend.listener import PagersListener
from apps.pocsag.backend.listener import PocsagListener
from apps.rtl433.backend.listener import Rtl433Listener
from apps.acars.backend.listener import AcarsListener
from apps.radio.backend.listener import RtlListener
from src.audio import sdr_registry


class TestReceiveRegions(unittest.IsolatedAsyncioTestCase):
    async def test_missing_frequency_never_opens_hardware(self):
        for factory in (PagersListener, PocsagListener, Rtl433Listener, AcarsListener):
            with self.subTest(receiver=factory.__name__), patch('shutil.which', return_value='tool'), patch('asyncio.create_subprocess_exec') as spawn:
                with self.assertRaises(ValueError):
                    await factory().start()
                spawn.assert_not_called()
                self.assertIsNone(sdr_registry.current_owner())

    async def test_invalid_frequency_never_opens_hardware(self):
        for factory in (PagersListener, PocsagListener, Rtl433Listener):
            for value in (0, 23, 1767, float('nan'), float('inf'), True):
                with self.subTest(receiver=factory.__name__, value=value), patch('shutil.which', return_value='tool'), patch('asyncio.create_subprocess_exec') as spawn:
                    with self.assertRaises(ValueError):
                        await factory().start(frequency_mhz=value)
                    spawn.assert_not_called()

    async def test_region_and_explicit_fm_audio_selection(self):
        self.assertEqual(RtlListener(region='US').deemphasis_us, 75)
        self.assertEqual(RtlListener(region='EU_868').deemphasis_us, 50)
        self.assertEqual(RtlListener(region='US', deemphasis_us=50).deemphasis_us, 50)
        for region in ('UNKNOWN', 'UNSUPPORTED', 'ANZ'):
            receiver = RtlListener(region=region)
            self.assertIsNone(receiver.deemphasis_us)
            with self.assertRaises(ValueError):
                await receiver.tune(100_000_000, mode='wfm')

    def test_configured_receive_frequencies_survive_initialization(self):
        for factory in (PagersListener, PocsagListener, Rtl433Listener):
            self.assertEqual(factory(frequency_mhz=155.5).status()['frequency_mhz'], 155.5)
        self.assertEqual(AcarsListener(frequencies=['131.550']).status()['frequencies'], ['131.550'])
