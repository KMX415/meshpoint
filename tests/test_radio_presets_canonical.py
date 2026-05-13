"""Lock MODEM_PRESETS to the upstream Meshtastic spec.

Each preset's (spreading_factor, bandwidth_khz, coding_rate) tuple
must match the canonical Meshtastic firmware values to avoid silent
drift like the v0.7.1-and-earlier bug where Short and Medium presets
shipped with CR 4/8 instead of 4/5, costing ~60% extra airtime per TX.

Reference: https://meshtastic.org/docs/overview/radio-settings/
"""

from __future__ import annotations

import unittest

from src.radio.presets import (
    MODEM_PRESETS,
    all_presets_list,
    get_preset,
    preset_from_params,
)

# Canonical (sf, bw_khz, cr) per upstream Meshtastic firmware
# RadioInterface.cpp. Keys must match MODEM_PRESETS keys exactly.
CANONICAL: dict[str, tuple[int, float, str]] = {
    "SHORT_TURBO":    (7,  500,   "4/5"),
    "SHORT_FAST":     (7,  250,   "4/5"),
    "SHORT_SLOW":     (8,  250,   "4/5"),
    "MEDIUM_FAST":    (9,  250,   "4/5"),
    "MEDIUM_SLOW":    (10, 250,   "4/5"),
    "LONG_FAST":      (11, 250,   "4/5"),
    "LONG_TURBO":     (11, 500,   "4/8"),
    "LONG_MODERATE":  (11, 125,   "4/8"),
    "LONG_SLOW":      (12, 125,   "4/8"),
    "VERY_LONG_SLOW": (12, 62.5,  "4/8"),
}


class TestPresetCanonicalValues(unittest.TestCase):

    def test_full_preset_coverage(self):
        """MODEM_PRESETS keys exactly match the canonical preset set."""
        self.assertEqual(set(MODEM_PRESETS.keys()), set(CANONICAL.keys()))

    def test_each_preset_matches_meshtastic_spec(self):
        """Every preset's (sf, bw, cr) tuple matches upstream firmware."""
        for name, expected in CANONICAL.items():
            with self.subTest(preset=name):
                p = MODEM_PRESETS[name]
                actual = (p.spreading_factor, p.bandwidth_khz, p.coding_rate)
                self.assertEqual(
                    actual,
                    expected,
                    f"{name} drifted from upstream spec",
                )

    def test_get_preset_round_trip(self):
        """get_preset() returns the same instance MODEM_PRESETS holds."""
        for name in CANONICAL:
            with self.subTest(preset=name):
                self.assertIs(get_preset(name), MODEM_PRESETS[name])
                self.assertIs(get_preset(name.lower()), MODEM_PRESETS[name])

    def test_reverse_lookup_round_trips(self):
        """preset_from_params(sf, bw, cr) returns the original preset name."""
        for name, (sf, bw, cr) in CANONICAL.items():
            with self.subTest(preset=name):
                self.assertEqual(preset_from_params(sf, bw, cr), name)

    def test_all_presets_list_includes_every_canonical_entry(self):
        """API-facing all_presets_list() exposes every canonical preset."""
        api_names = {entry["name"] for entry in all_presets_list()}
        self.assertEqual(api_names, set(CANONICAL.keys()))

    def test_long_turbo_is_tx_capable(self):
        """LongTurbo mirrors ShortTurbo's tx_capable=True (BW500 region-aware)."""
        self.assertTrue(MODEM_PRESETS["LONG_TURBO"].tx_capable)
        self.assertTrue(MODEM_PRESETS["SHORT_TURBO"].tx_capable)

    def test_very_long_slow_is_not_tx_capable(self):
        """Deprecated VeryLongSlow remains RX-only per existing constraint."""
        self.assertFalse(MODEM_PRESETS["VERY_LONG_SLOW"].tx_capable)


if __name__ == "__main__":
    unittest.main()
