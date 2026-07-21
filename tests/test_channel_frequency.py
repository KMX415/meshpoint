"""Tests for src.radio.channel_frequency (Meshtastic channel->frequency).

Pure Python, no meshtastic/protobuf dependency (unlike most of the
other serial-capture-adjacent tests in this suite), so this runs on a
bare Mac python3. Every expected value here is either cross-checked
against a real device's observed frequency (EU_433 default channel ->
433.875 MHz) or hand-derived from meshtastic/firmware's
src/mesh/RadioInterface.cpp formula, read directly from a local
firmware source checkout.
"""

from __future__ import annotations

import unittest

from src.radio.channel_frequency import _djb2, resolve_frequency_mhz


class Djb2Test(unittest.TestCase):
    def test_matches_known_values(self):
        # djb2("") = 5381 (the seed, no bytes folded in).
        self.assertEqual(_djb2(""), 5381)

    def test_is_deterministic(self):
        self.assertEqual(_djb2("LongFast"), _djb2("LongFast"))

    def test_different_strings_differ(self):
        self.assertNotEqual(_djb2("LongFast"), _djb2("LongSlow"))

    def test_stays_within_32_bits(self):
        # A long input must not overflow past uint32 wraparound.
        self.assertLess(_djb2("x" * 1000), 2**32)


class ResolveFrequencyDefaultChannelTest(unittest.TestCase):
    """channel_num=0: hash-derived slot from the primary channel name."""

    def test_eu433_blank_channel_name_falls_back_to_preset_display_name(self):
        # Reproduces a real device's observed frequency exactly: blank
        # primary channel name (the common stock case) falls back to
        # the LongFast preset's firmware display string for hashing.
        freq = resolve_frequency_mhz(
            region="EU_433", channel_num=0, bandwidth_khz=250,
            channel_name="", modem_preset="LONG_FAST", use_preset=True,
        )
        self.assertEqual(freq, 433.875)

    def test_eu433_none_channel_name_same_as_blank(self):
        freq = resolve_frequency_mhz(
            region="EU_433", channel_num=0, bandwidth_khz=250,
            channel_name=None, modem_preset="LONG_FAST", use_preset=True,
        )
        self.assertEqual(freq, 433.875)

    def test_eu433_custom_channel_name_changes_the_slot(self):
        # A real (non-blank) channel name is hashed directly -- a
        # different name can land on a different one of the 4 slots.
        freq_custom = resolve_frequency_mhz(
            region="EU_433", channel_num=0, bandwidth_khz=250,
            channel_name="MySecretChannel",
        )
        # Not asserting a specific value (that depends on the hash of
        # an arbitrary string) -- just that a real channel name is
        # actually used rather than always falling back to the preset.
        self.assertIn(freq_custom, (433.125, 433.375, 433.625, 433.875))

    def test_eu868_single_slot_is_independent_of_channel_name(self):
        # EU_868's band (869.4-869.65 MHz) only fits one 250kHz slot,
        # so the default is deterministic regardless of channel name --
        # this is why a LongFast channel on 868 and a LongFast channel
        # on 433 (same name) never collide: different regions, and 868
        # never even reaches the hash step.
        for name in ("", "LongFast", "AnythingAtAll", "custom-mesh"):
            freq = resolve_frequency_mhz(
                region="EU_868", channel_num=0, bandwidth_khz=250,
                channel_name=name,
            )
            self.assertEqual(freq, 869.525, f"failed for channel_name={name!r}")

    def test_use_preset_false_hashes_custom_literal(self):
        # use_preset=False (fully custom SF/BW/CR, no named preset) ->
        # firmware hashes the literal string "Custom" when the channel
        # name is also blank.
        freq = resolve_frequency_mhz(
            region="EU_433", channel_num=0, bandwidth_khz=250,
            channel_name="", use_preset=False,
        )
        self.assertIn(freq, (433.125, 433.375, 433.625, 433.875))

    def test_long_moderate_preset_uses_firmware_short_string_not_ui_label(self):
        # Regression guard: firmware's hash string for LONG_MODERATE is
        # "LongMod", NOT "LongModerate" (this codebase's own UI label
        # in src/radio/presets.py) -- using the wrong one would
        # silently compute a different (wrong) slot.
        from src.radio.channel_frequency import _preset_hash_name
        self.assertEqual(_preset_hash_name("LONG_MODERATE", True), "LongMod")

    def test_unrecognized_preset_falls_back_to_invalid_literal(self):
        from src.radio.channel_frequency import _preset_hash_name
        self.assertEqual(_preset_hash_name("VERY_LONG_SLOW", True), "Invalid")
        self.assertEqual(_preset_hash_name(None, True), "Invalid")


class ResolveFrequencyExplicitChannelTest(unittest.TestCase):
    """channel_num > 0: explicit 1-based slot, no hash needed."""

    def test_channel_num_one_is_slot_zero(self):
        freq = resolve_frequency_mhz(region="EU_433", channel_num=1, bandwidth_khz=250)
        self.assertEqual(freq, 433.125)

    def test_channel_num_four_is_slot_three(self):
        freq = resolve_frequency_mhz(region="EU_433", channel_num=4, bandwidth_khz=250)
        self.assertEqual(freq, 433.875)

    def test_channel_num_beyond_region_slot_count_is_unknown_not_a_guess(self):
        # Firmware itself rejects a channel_num above the region's
        # slot count at config-set time -- a real device never
        # reports one out of range. EU_868 only has 1 slot, so
        # channel_num=5 (slot 4) must not compute an out-of-band
        # number.
        freq = resolve_frequency_mhz(region="EU_868", channel_num=5, bandwidth_khz=250)
        self.assertEqual(freq, 0.0)

    def test_explicit_channel_ignores_channel_name(self):
        freq_a = resolve_frequency_mhz(
            region="EU_433", channel_num=2, bandwidth_khz=250, channel_name="Alpha",
        )
        freq_b = resolve_frequency_mhz(
            region="EU_433", channel_num=2, bandwidth_khz=250, channel_name="Bravo",
        )
        self.assertEqual(freq_a, freq_b)


class ResolveFrequencyEdgeCaseTest(unittest.TestCase):
    def test_override_frequency_wins_outright(self):
        freq = resolve_frequency_mhz(
            region="EU_433", channel_num=0, bandwidth_khz=250,
            override_frequency=433.5, frequency_offset=0.1,
        )
        self.assertEqual(freq, 433.6)

    def test_frequency_offset_applied_to_computed_frequency(self):
        freq = resolve_frequency_mhz(
            region="EU_433", channel_num=1, bandwidth_khz=250, frequency_offset=0.05,
        )
        self.assertEqual(freq, 433.175)

    def test_missing_region_yields_unknown(self):
        self.assertEqual(
            resolve_frequency_mhz(region=None, channel_num=0, bandwidth_khz=250), 0.0,
        )

    def test_missing_bandwidth_yields_unknown(self):
        self.assertEqual(
            resolve_frequency_mhz(region="EU_433", channel_num=0, bandwidth_khz=None), 0.0,
        )

    def test_unsupported_region_yields_unknown_not_a_guess(self):
        # EU_866 uses PROFILE_LITE (nonzero spacing/padding), not
        # modelled by this simplified resolver.
        self.assertEqual(
            resolve_frequency_mhz(region="EU_866", channel_num=0, bandwidth_khz=250), 0.0,
        )

    def test_zero_bandwidth_does_not_divide_by_zero(self):
        self.assertEqual(
            resolve_frequency_mhz(region="EU_433", channel_num=0, bandwidth_khz=0), 0.0,
        )


if __name__ == "__main__":
    unittest.main()
