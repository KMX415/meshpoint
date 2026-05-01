"""Tests for ``_resolve_radio_frequency`` and the regional fallback tables.

The resolver lets ``radio.frequency_mhz`` default to ``None`` in config
and pick a sensible value at runtime: an explicit MHz wins, otherwise a
configured slot is converted via the Meshtastic formula, otherwise a
regional default is used.
"""

from __future__ import annotations

import unittest

from src.config import (
    _REGION_DEFAULT_FREQ,
    _REGION_FREQ_START,
    RadioConfig,
    _resolve_radio_frequency,
)


class TestResolveRadioFrequency(unittest.TestCase):
    def _radio(self, **overrides) -> RadioConfig:
        radio = RadioConfig()
        radio.frequency_mhz = None
        radio.slot = None
        for k, v in overrides.items():
            setattr(radio, k, v)
        return radio

    def test_explicit_frequency_wins_over_slot_and_region(self):
        radio = self._radio(region="US", slot=20, frequency_mhz=903.0)
        _resolve_radio_frequency(radio)
        self.assertEqual(radio.frequency_mhz, 903.0)

    def test_explicit_frequency_wins_over_region_default(self):
        radio = self._radio(region="EU_868", frequency_mhz=868.5)
        _resolve_radio_frequency(radio)
        self.assertEqual(radio.frequency_mhz, 868.5)

    def test_slot_resolves_us_longfast(self):
        # US LongFast slot 20 = 902.0 + 0.125 + 19*0.25 = 906.875 MHz
        radio = self._radio(region="US", slot=20, bandwidth_khz=250.0)
        _resolve_radio_frequency(radio)
        self.assertEqual(radio.frequency_mhz, 906.875)

    def test_slot_resolves_eu_longfast(self):
        # EU_868 LongFast slot 1 = 863.0 + 0.125 + 0*0.25 = 863.125 MHz
        radio = self._radio(region="EU_868", slot=1, bandwidth_khz=250.0)
        _resolve_radio_frequency(radio)
        self.assertEqual(radio.frequency_mhz, 863.125)

    def test_slot_resolves_125khz_bw(self):
        # US 125 kHz slot 1 = 902.0 + 0.0625 + 0 = 902.0625 MHz
        radio = self._radio(region="US", slot=1, bandwidth_khz=125.0)
        _resolve_radio_frequency(radio)
        self.assertEqual(radio.frequency_mhz, 902.0625)

    def test_us_default_is_906_875(self):
        radio = self._radio(region="US")
        _resolve_radio_frequency(radio)
        self.assertEqual(radio.frequency_mhz, 906.875)

    def test_eu_default_is_869_525(self):
        radio = self._radio(region="EU_868")
        _resolve_radio_frequency(radio)
        self.assertEqual(radio.frequency_mhz, 869.525)

    def test_anz_default_is_916(self):
        radio = self._radio(region="ANZ")
        _resolve_radio_frequency(radio)
        self.assertEqual(radio.frequency_mhz, 916.0)

    def test_in_default_is_865_4625(self):
        radio = self._radio(region="IN")
        _resolve_radio_frequency(radio)
        self.assertEqual(radio.frequency_mhz, 865.4625)

    def test_kr_default_is_921_9(self):
        radio = self._radio(region="KR")
        _resolve_radio_frequency(radio)
        self.assertEqual(radio.frequency_mhz, 921.9)

    def test_sg_default_is_923(self):
        radio = self._radio(region="SG_923")
        _resolve_radio_frequency(radio)
        self.assertEqual(radio.frequency_mhz, 923.0)

    def test_unknown_region_falls_back_to_us_default(self):
        radio = self._radio(region="MARS")
        _resolve_radio_frequency(radio)
        self.assertEqual(radio.frequency_mhz, 906.875)

    def test_slot_with_unknown_region_falls_through_to_default(self):
        # No FREQ_START entry for region: slot is ignored, falls
        # through to _REGION_DEFAULT_FREQ.
        radio = self._radio(region="MARS", slot=20, bandwidth_khz=250.0)
        _resolve_radio_frequency(radio)
        self.assertEqual(radio.frequency_mhz, 906.875)


class TestRegionTables(unittest.TestCase):
    def test_freq_start_covers_all_supported_regions(self):
        from src.cli.setup_wizard import SUPPORTED_REGIONS

        for region in SUPPORTED_REGIONS:
            with self.subTest(region=region):
                self.assertIn(region, _REGION_FREQ_START)

    def test_default_freq_covers_all_supported_regions(self):
        from src.cli.setup_wizard import SUPPORTED_REGIONS

        for region in SUPPORTED_REGIONS:
            with self.subTest(region=region):
                self.assertIn(region, _REGION_DEFAULT_FREQ)


if __name__ == "__main__":
    unittest.main()
