"""Tests for the reticulum plugin's config state.

Pure Python -- backend.state has no FastAPI / RNS import.
"""

from __future__ import annotations

import unittest
from unittest import mock

from apps.reticulum.backend import state


class TestReticulumState(unittest.TestCase):
    def tearDown(self) -> None:
        state.init({})  # reset to defaults for the next test

    def test_defaults_keep_external_interfaces_off(self) -> None:
        state.init({})
        self.assertEqual(state.display_name(), "Meshpoint")
        self.assertEqual(state.reticulum_config_dir(), "data/reticulum/rns_config")
        self.assertEqual(state.identity_path(), "data/reticulum/identity")
        self.assertEqual(state.lxmf_storage_dir(), "data/reticulum/lxmf")
        d = state.to_dict()
        self.assertIsNone(d["rnode_frequency_hz"])
        self.assertEqual(d["backbone_host"], "")
        self.assertFalse(d["rnode_enabled"])
        self.assertFalse(d["backbone_enabled"])
        self.assertEqual(d["backbone_port"], 4242)
        self.assertEqual(d["rnode_serial_port"], "")
        self.assertIs(d["rnode_enabled"], False)
        self.assertIs(d["backbone_enabled"], False)

    def test_user_values_override_defaults(self) -> None:
        state.init({
            "display_name": "PD2EMC Meshpoint",
            "reticulum_config_dir": "/opt/meshpoint/data/reticulum/rns_config",
            "rnode_serial_port": "/dev/serial/by-id/usb-RNode-x",
            "rnode_frequency_hz": 867_000_000,
            "backbone_port": 4243,
        })
        self.assertEqual(state.display_name(), "PD2EMC Meshpoint")
        self.assertEqual(
            state.reticulum_config_dir(), "/opt/meshpoint/data/reticulum/rns_config",
        )
        d = state.to_dict()
        self.assertEqual(d["rnode_serial_port"], "/dev/serial/by-id/usb-RNode-x")
        self.assertEqual(d["rnode_frequency_hz"], 867_000_000)
        self.assertEqual(d["backbone_port"], 4243)

    def test_rnode_and_backbone_enabled_flags_can_be_turned_off(self) -> None:
        # False is a legitimate override, not "unset" -- must not fall back
        # to the True default (same class of bug as node_enabled/False).
        state.init({"rnode_enabled": False, "backbone_enabled": False})
        d = state.to_dict()
        self.assertIs(d["rnode_enabled"], False)
        self.assertIs(d["backbone_enabled"], False)

    def test_empty_string_and_missing_keys_fall_back_to_defaults(self) -> None:
        # "" is what a cleared YAML field looks like -- treat it as unset.
        state.init({"display_name": "", "backbone_host": None})
        self.assertEqual(state.display_name(), "Meshpoint")
        self.assertEqual(state.to_dict()["backbone_host"], "")

    def test_rnode_serial_port_empty_string_is_taken_verbatim(self) -> None:
        state.init({"rnode_serial_port": ""})
        self.assertEqual(state.to_dict()["rnode_serial_port"], "")

    def test_node_config_defaults_off_name_falls_back_to_display_name(self) -> None:
        state.init({"display_name": "PD2EMC Meshpoint"})
        nc = state.node_config()
        self.assertFalse(nc["enabled"])
        self.assertEqual(nc["name"], "PD2EMC Meshpoint")  # blank node_name -> display_name
        self.assertEqual(nc["pages_dir"], "data/reticulum/pages")
        self.assertFalse(nc["talkback_enabled"])

    def test_node_config_uses_explicit_values(self) -> None:
        state.init({
            "display_name": "PD2EMC Meshpoint",
            "node_enabled": True,
            "node_name": "PD2EMC BBS",
            "node_announce_interval_s": 3600,
            "talkback_enabled": True,
        })
        nc = state.node_config()
        self.assertTrue(nc["enabled"])
        self.assertEqual(nc["name"], "PD2EMC BBS")
        self.assertEqual(nc["announce_interval_s"], 3600)
        self.assertTrue(nc["talkback_enabled"])

    def test_propagation_config_defaults_off(self) -> None:
        state.init({})
        pc = state.propagation_config()
        self.assertFalse(pc["enabled"])
        self.assertEqual(pc["storage_limit_mb"], 250)
        self.assertEqual(state.notify_url(), "")

    def test_propagation_config_explicit(self) -> None:
        state.init({
            "propagation_enabled": True,
            "propagation_storage_limit_mb": 1000,
            "notify_url": "  https://ntfy.sh/x  ",
        })
        pc = state.propagation_config()
        self.assertTrue(pc["enabled"])
        self.assertEqual(pc["storage_limit_mb"], 1000)
        self.assertEqual(state.notify_url(), "https://ntfy.sh/x")  # stripped


class TestReticulumStateWrites(unittest.TestCase):
    def setUp(self) -> None:
        state.init({})
        self._persist = mock.patch.object(state, "_persist")
        self._persist.start()

    def tearDown(self) -> None:
        self._persist.stop()
        state.init({})

    def test_set_config_merges_and_persists(self) -> None:
        state.set_config({"display_name": "PD2EMC", "backbone_port": 4243})
        self.assertEqual(state.display_name(), "PD2EMC")
        self.assertEqual(state.to_dict()["backbone_port"], 4243)
        state._persist.assert_called_once()

    def test_set_config_ignores_unknown_keys(self) -> None:
        state.set_config({"display_name": "X", "enabled": True, "bogus": 1})
        d = state.to_dict()
        self.assertEqual(d["display_name"], "X")
        self.assertNotIn("enabled", d)  # enabled is the Settings->Plugins toggle
        self.assertNotIn("bogus", d)


class TestReticulumStatePersistMerge(unittest.TestCase):
    """_persist() must preserve fields it doesn't manage (like "enabled")
    even though to_dict() never includes them -- save_section_to_yaml does
    a shallow per-section dict.update()."""

    def tearDown(self) -> None:
        state.init({})

    def test_persist_merges_over_current_saved_config(self) -> None:
        state.init({"display_name": "Merged"})
        with mock.patch.object(
            state, "_current_saved_config",
            return_value={"enabled": True, "extra": "kept"},
        ), mock.patch("src.config.save_section_to_yaml") as mock_save:
            state._persist()
        mock_save.assert_called_once()
        (section, values), _ = mock_save.call_args
        self.assertEqual(section, "plugins")
        self.assertTrue(values["reticulum"]["enabled"])
        self.assertEqual(values["reticulum"]["extra"], "kept")
        self.assertEqual(values["reticulum"]["display_name"], "Merged")


class TestTelemetryCollectors(unittest.TestCase):
    def tearDown(self) -> None:
        state.init({})

    def test_multiline_collectors_parsed_normalised_deduped(self) -> None:
        state.init({"telemetry_enabled": True, "telemetry_collector":
                    f"<{'ab' * 16}>\n{'CD' * 16}\n{'ab' * 16}\n  \n"})
        cfg = state.telemetry_config()
        self.assertEqual(cfg["collectors"], ["ab" * 16, "cd" * 16])
        self.assertEqual(cfg["collector"], "ab" * 16)

    def test_comma_and_colon_forms(self) -> None:
        state.init({"telemetry_collector": "aa:bb:cc:dd:ee:ff:00:11, " + "bb" * 16})
        self.assertEqual(
            state.telemetry_config()["collectors"],
            ["aabbccddeeff0011", "bb" * 16],
        )

    def test_empty(self) -> None:
        state.init({})
        self.assertEqual(state.telemetry_config()["collectors"], [])
        self.assertEqual(state.telemetry_config()["collector"], "")


class TestExtraInterfaces(unittest.TestCase):
    def tearDown(self) -> None:
        state.init({})

    def test_defaults_empty(self) -> None:
        state.init({})
        self.assertEqual(state.extra_interfaces(), [])

    def test_reads_a_list_of_dicts(self) -> None:
        state.init({"extra_interfaces": [
            {"name": "A", "type": "TCPClientInterface"},
            "not a dict",
            {"name": "B", "type": "UDPInterface"},
        ]})
        got = state.extra_interfaces()
        self.assertEqual([e["name"] for e in got], ["A", "B"])

    def test_non_list_is_empty(self) -> None:
        state.init({"extra_interfaces": "nope"})
        self.assertEqual(state.extra_interfaces(), [])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
