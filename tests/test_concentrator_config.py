"""Tests for ConcentratorChannelPlan.from_radio_config().

Validates that spreading_factor and bandwidth_khz are respected
for all regions, not just when they match the LongFast defaults.
"""

from __future__ import annotations

import unittest

from src.hal.concentrator_config import ConcentratorChannelPlan


def _core_available() -> bool:
    try:
        ConcentratorChannelPlan.for_region("US")
        return True
    except RuntimeError:
        return False


@unittest.skipUnless(_core_available(), "Core module not available (stub only)")
class TestFromRadioConfigLongFast(unittest.TestCase):
    """LongFast (SF11/BW250) at default frequency uses hardcoded preset."""

    def test_us_longfast_uses_preset(self):
        plan = ConcentratorChannelPlan.from_radio_config(
            region="US", frequency_mhz=906.875,
            spreading_factor=11, bandwidth_khz=250.0,
        )
        sf = plan.single_sf_channel.spreading_factor
        self.assertEqual(sf, 11)
        self.assertEqual(plan.single_sf_channel.bandwidth_khz, 250)
        self.assertEqual(plan.single_sf_channel.frequency_hz, 906_875_000)
        self.assertEqual(len(plan.multi_sf_channels), 8)

    def test_eu868_longfast_uses_preset(self):
        plan = ConcentratorChannelPlan.from_radio_config(
            region="EU_868", frequency_mhz=869.525,
            spreading_factor=11, bandwidth_khz=250.0,
        )
        sf = plan.single_sf_channel.spreading_factor
        self.assertEqual(sf, 11)
        self.assertEqual(plan.single_sf_channel.bandwidth_khz, 250)
        self.assertEqual(plan.radio_0_freq_hz, 869_525_000)
        self.assertEqual(plan.radio_1_freq_hz, 869_525_000)

    def test_anz_longfast_uses_preset(self):
        plan = ConcentratorChannelPlan.from_radio_config(
            region="ANZ", frequency_mhz=919.875,
            spreading_factor=11, bandwidth_khz=250.0,
        )
        self.assertEqual(plan.single_sf_channel.spreading_factor, 11)
        self.assertEqual(plan.single_sf_channel.frequency_hz, 919_875_000)


@unittest.skipUnless(_core_available(), "Core module not available (stub only)")
class TestFromRadioConfigNonLongFast(unittest.TestCase):
    """Non-LongFast presets at default frequency must respect SF and BW."""

    def test_eu868_mediumfast_respects_sf9(self):
        plan = ConcentratorChannelPlan.from_radio_config(
            region="EU_868", frequency_mhz=869.525,
            spreading_factor=9, bandwidth_khz=250.0,
        )
        self.assertEqual(plan.single_sf_channel.spreading_factor, 9)
        self.assertEqual(plan.single_sf_channel.bandwidth_khz, 250)
        self.assertEqual(plan.single_sf_channel.frequency_hz, 869_525_000)

    def test_eu868_shortfast_respects_sf7(self):
        plan = ConcentratorChannelPlan.from_radio_config(
            region="EU_868", frequency_mhz=869.525,
            spreading_factor=7, bandwidth_khz=250.0,
        )
        self.assertEqual(plan.single_sf_channel.spreading_factor, 7)

    def test_us_mediumfast_respects_sf9(self):
        plan = ConcentratorChannelPlan.from_radio_config(
            region="US", frequency_mhz=906.875,
            spreading_factor=9, bandwidth_khz=250.0,
        )
        self.assertEqual(plan.single_sf_channel.spreading_factor, 9)
        self.assertEqual(plan.single_sf_channel.bandwidth_khz, 250)
        self.assertEqual(plan.single_sf_channel.frequency_hz, 906_875_000)

    def test_us_shortturbo_respects_sf7_bw500(self):
        plan = ConcentratorChannelPlan.from_radio_config(
            region="US", frequency_mhz=906.875,
            spreading_factor=7, bandwidth_khz=500.0,
        )
        self.assertEqual(plan.single_sf_channel.spreading_factor, 7)
        self.assertEqual(plan.single_sf_channel.bandwidth_khz, 500)

    def test_anz_mediumfast_respects_sf9(self):
        plan = ConcentratorChannelPlan.from_radio_config(
            region="ANZ", frequency_mhz=919.875,
            spreading_factor=9, bandwidth_khz=250.0,
        )
        self.assertEqual(plan.single_sf_channel.spreading_factor, 9)


@unittest.skipUnless(_core_available(), "Core module not available (stub only)")
class TestFromRadioConfigCustomFrequency(unittest.TestCase):
    """Custom (non-default) frequencies with non-LongFast SF."""

    def test_eu868_custom_freq_sf9(self):
        plan = ConcentratorChannelPlan.from_radio_config(
            region="EU_868", frequency_mhz=869.500,
            spreading_factor=9, bandwidth_khz=250.0,
        )
        self.assertEqual(plan.single_sf_channel.spreading_factor, 9)
        self.assertEqual(plan.single_sf_channel.frequency_hz, 869_500_000)

    def test_us_custom_freq_sf9(self):
        plan = ConcentratorChannelPlan.from_radio_config(
            region="US", frequency_mhz=910.0,
            spreading_factor=9, bandwidth_khz=250.0,
        )
        self.assertEqual(plan.single_sf_channel.spreading_factor, 9)
        self.assertEqual(plan.single_sf_channel.frequency_hz, 910_000_000)

    def test_no_region_uses_centered_plan(self):
        plan = ConcentratorChannelPlan.from_radio_config(
            region="", frequency_mhz=915.0,
            spreading_factor=7, bandwidth_khz=500.0,
        )
        self.assertEqual(plan.single_sf_channel.spreading_factor, 7)
        self.assertEqual(plan.single_sf_channel.bandwidth_khz, 500)


@unittest.skipUnless(_core_available(), "Core module not available (stub only)")
class TestFromRadioConfigValidation(unittest.TestCase):
    """Band limit and region validation."""

    def test_out_of_band_raises(self):
        with self.assertRaises(ValueError):
            ConcentratorChannelPlan.from_radio_config(
                region="EU_868", frequency_mhz=900.0,
                spreading_factor=11, bandwidth_khz=250.0,
            )

    def test_unsupported_region_raises(self):
        with self.assertRaises(ValueError):
            ConcentratorChannelPlan.from_radio_config(
                region="INVALID", frequency_mhz=906.875,
            )

    def test_eu868_narrow_plan_structure(self):
        """EU_868 non-LongFast still gets narrow plan (2 active multi-SF)."""
        plan = ConcentratorChannelPlan.from_radio_config(
            region="EU_868", frequency_mhz=869.525,
            spreading_factor=9, bandwidth_khz=250.0,
        )
        enabled = [ch for ch in plan.multi_sf_channels if ch.enabled]
        disabled = [ch for ch in plan.multi_sf_channels if not ch.enabled]
        self.assertEqual(len(enabled), 2)
        self.assertEqual(len(disabled), 6)

    def test_us_nonlongfast_gets_centered_plan(self):
        """US non-LongFast gets centered plan (8 active multi-SF)."""
        plan = ConcentratorChannelPlan.from_radio_config(
            region="US", frequency_mhz=906.875,
            spreading_factor=9, bandwidth_khz=250.0,
        )
        self.assertEqual(len(plan.multi_sf_channels), 8)
        self.assertTrue(all(ch.enabled for ch in plan.multi_sf_channels))


if __name__ == "__main__":
    unittest.main()
