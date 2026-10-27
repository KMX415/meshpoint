"""Regional defaults must never retune an explicitly configured RNode."""
import unittest
from unittest.mock import patch
from pydantic import ValidationError
from apps.reticulum.backend import regional, state
from apps.reticulum.backend.config_routes import ReticulumUpdate
from apps.reticulum.backend.rns_config import render_config
from src.cli.setup_wizard import SUPPORTED_REGIONS


class TestReticulumRegions(unittest.TestCase):
    def tearDown(self):
        state.init({})

    def test_every_supported_region_has_a_profile(self):
        self.assertEqual(set(SUPPORTED_REGIONS), set(regional.PROFILES))
        bands = {"US": (902, 928), "EU_868": (869.4, 869.65), "ANZ": (915, 928),
                 "IN": (865, 868), "KR": (920, 923), "SG_923": (920, 925)}
        for region, (low, high) in bands.items():
            with self.subTest(region=region):
                state.init({}, region=region)
                cfg = state.to_dict()
                half = cfg["rnode_bandwidth_hz"] / 2
                self.assertGreaterEqual(cfg["rnode_frequency_hz"] - half, low * 1e6)
                self.assertLessEqual(cfg["rnode_frequency_hz"] + half, high * 1e6)
                self.assertFalse(cfg["rnode_enabled"])
                ReticulumUpdate.model_validate(cfg)
                rendered = render_config({**cfg, "rnode_enabled": True, "rnode_serial_port": "test-port"})
                self.assertIn("airtime_limit_long = 1", rendered)
                self.assertIn("airtime_limit_short = 10", rendered)

    def test_us_and_anz_use_wide_starting_profiles(self):
        for region in ("US", "ANZ"):
            self.assertEqual(regional.defaults(region)["rnode_bandwidth_hz"], 500_000)
        self.assertEqual(regional.defaults("US")["rnode_frequency_hz"], 915_000_000)

    def test_explicit_settings_survive_region_changes(self):
        custom = dict(zip(regional.RADIO_KEYS, (867_000_000, 62_500, 0, 9, 8, 3, 0.5)))
        for region in (*SUPPORTED_REGIONS, "UNKNOWN"):
            state.init(custom, region=region)
            actual = state.to_dict()
            self.assertEqual({k: actual[k] for k in custom}, custom)

    def test_unknown_region_has_no_frequency_or_european_fallback(self):
        state.init({}, region="UNSUPPORTED")
        cfg = state.to_dict()
        self.assertIsNone(cfg["rnode_frequency_hz"])
        self.assertFalse(cfg["radio_profile_available"])
        ReticulumUpdate.model_validate(cfg)
        enabled = {**cfg, "rnode_enabled": True, "rnode_serial_port": "test-port"}
        with self.assertRaises(ValidationError):
            ReticulumUpdate.model_validate(enabled)
        with self.assertRaises(ValueError):
            render_config(enabled)
        enabled["rnode_frequency_hz"] = 915_000_000
        self.assertIn("frequency = 915000000", render_config(enabled))

    def test_metadata_not_persisted_and_blank_limits_resolve_consistently(self):
        state.init({}, region="US")
        with patch.object(state, "_current_saved_config", return_value={"enabled": True}):
            with patch("src.config.save_section_to_yaml") as save:
                state.set_config({"rnode_airtime_limit_long": None})
        saved = save.call_args.args[1]["reticulum"]
        self.assertTrue(saved["enabled"])
        self.assertEqual(saved["rnode_airtime_limit_long"], 1)
        self.assertNotIn("radio_region", saved)
        self.assertNotIn("radio_defaults", saved)

    def test_airtime_bounds_are_checked(self):
        for value in (0, -1, 101, float("nan"), float("inf")):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                ReticulumUpdate(rnode_airtime_limit_long=value)
