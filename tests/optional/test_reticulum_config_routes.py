"""Tests for the ReticulumUpdate pydantic model's validators
(config_routes.py). No FastAPI route/DB involved -- pure model validation,
importable on the Mac (no aiosqlite pulled in)."""

from __future__ import annotations

import unittest

from pydantic import ValidationError

from apps.reticulum.backend.config_routes import ReticulumUpdate

_REQUIRED = {"rnode_frequency_hz": 869_463_000}


class TestTalkbackNeedsNode(unittest.TestCase):
    def test_talkback_without_node_hosting_is_rejected(self) -> None:
        with self.assertRaises(ValidationError) as cm:
            ReticulumUpdate(**_REQUIRED, talkback_enabled=True, node_enabled=False)
        self.assertIn("talk-back bot", str(cm.exception))

    def test_talkback_with_node_hosting_is_accepted(self) -> None:
        model = ReticulumUpdate(**_REQUIRED, talkback_enabled=True, node_enabled=True)
        self.assertTrue(model.talkback_enabled)

    def test_talkback_off_needs_no_node_hosting(self) -> None:
        model = ReticulumUpdate(**_REQUIRED, talkback_enabled=False, node_enabled=False)
        self.assertFalse(model.talkback_enabled)

    def test_defaults_to_off(self) -> None:
        model = ReticulumUpdate(**_REQUIRED)
        self.assertFalse(model.talkback_enabled)


class TestExtraInterfaces(unittest.TestCase):
    def _iface(self, **kw):
        base = {"name": "X", "type": "TCPClientInterface",
                "target_host": "h.example", "target_port": 4242}
        base.update(kw)
        return base

    def test_defaults_to_empty(self) -> None:
        self.assertEqual(ReticulumUpdate(**_REQUIRED).extra_interfaces, [])

    def test_valid_tcp_client(self) -> None:
        m = ReticulumUpdate(**_REQUIRED, extra_interfaces=[self._iface()])
        stored = m.extra_interfaces[0].to_stored()
        self.assertEqual(stored, {
            "name": "X", "type": "TCPClientInterface", "enabled": True,
            "target_host": "h.example", "target_port": 4242,
        })

    def test_reserved_name_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            ReticulumUpdate(**_REQUIRED, extra_interfaces=[self._iface(name="RNode LoRa")])

    def test_missing_type_field_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            ReticulumUpdate(**_REQUIRED, extra_interfaces=[
                {"name": "X", "type": "TCPClientInterface"},  # no target_host/port
            ])

    def test_duplicate_names_rejected(self) -> None:
        with self.assertRaises(ValidationError) as cm:
            ReticulumUpdate(**_REQUIRED, extra_interfaces=[
                self._iface(name="dup"), self._iface(name="Dup", target_host="y"),
            ])
        self.assertIn("unique", str(cm.exception))

    def test_udp_stored_fills_defaults(self) -> None:
        m = ReticulumUpdate(**_REQUIRED, extra_interfaces=[
            {"name": "lan", "type": "UDPInterface", "listen_port": 4242},
        ])
        s = m.extra_interfaces[0].to_stored()
        self.assertEqual(s["listen_ip"], "0.0.0.0")
        self.assertEqual(s["forward_ip"], "255.255.255.255")
        self.assertEqual(s["forward_port"], 4242)

    def test_only_extra_interface_satisfies_at_least_one(self) -> None:
        # rnode + backbone both off, but an active extra interface -> ok
        m = ReticulumUpdate(
            **_REQUIRED, rnode_enabled=False, backbone_enabled=False,
            extra_interfaces=[self._iface()],
        )
        self.assertEqual(len(m.extra_interfaces), 1)

    def test_all_interfaces_off_is_a_valid_starting_configuration(self):
        model = ReticulumUpdate(**_REQUIRED, rnode_enabled=False, backbone_enabled=False,
                                extra_interfaces=[self._iface(enabled=False)])
        self.assertFalse(model.rnode_enabled)
        self.assertFalse(model.backbone_enabled)

    def test_blank_is_fine(self) -> None:
        m = ReticulumUpdate(**_REQUIRED, propagation_outbound_node="")
        self.assertEqual(m.propagation_outbound_node, "")

    def test_valid_hash_is_normalised(self) -> None:
        m = ReticulumUpdate(**_REQUIRED, propagation_outbound_node="AB:CD" + "EF" * 14)
        self.assertEqual(m.propagation_outbound_node, "abcd" + "ef" * 14)

    def test_angle_bracket_form_is_accepted(self) -> None:
        # RNS's own <hex> display form (startup banner / "You:" line)
        m = ReticulumUpdate(**_REQUIRED, telemetry_collector="<" + "ab" * 16 + ">")
        self.assertEqual(m.telemetry_collector, "ab" * 16)

    def test_non_hex_is_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            ReticulumUpdate(**_REQUIRED, propagation_outbound_node="not-a-hash")

    def test_auto_sync_needs_a_node(self) -> None:
        with self.assertRaises(ValidationError) as cm:
            ReticulumUpdate(**_REQUIRED, propagation_auto_sync_interval_s=600)
        self.assertIn("outbound propagation node", str(cm.exception))

    def test_auto_sync_floor(self) -> None:
        with self.assertRaises(ValidationError):
            ReticulumUpdate(
                **_REQUIRED,
                propagation_outbound_node="ab" * 16,
                propagation_auto_sync_interval_s=120,
            )

    def test_auto_sync_with_node_and_valid_interval(self) -> None:
        m = ReticulumUpdate(
            **_REQUIRED,
            propagation_outbound_node="ab" * 16,
            propagation_auto_sync_interval_s=900,
        )
        self.assertEqual(m.propagation_auto_sync_interval_s, 900)


class TestTelemetryConfig(unittest.TestCase):
    def test_defaults_off(self) -> None:
        m = ReticulumUpdate(**_REQUIRED)
        self.assertFalse(m.telemetry_enabled)
        self.assertEqual(m.telemetry_interval_s, 900)

    def test_enabled_needs_a_collector(self) -> None:
        with self.assertRaises(ValidationError) as cm:
            ReticulumUpdate(**_REQUIRED, telemetry_enabled=True)
        self.assertIn("collector", str(cm.exception))

    def test_enabled_with_collector_ok_and_hash_normalised(self) -> None:
        m = ReticulumUpdate(
            **_REQUIRED, telemetry_enabled=True,
            telemetry_collector="AB:CD" + "EF" * 14,
        )
        self.assertTrue(m.telemetry_enabled)
        self.assertEqual(m.telemetry_collector, "abcd" + "ef" * 14)

    def test_bad_collector_hash_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            ReticulumUpdate(**_REQUIRED, telemetry_collector="xyz")

    def test_multiline_collectors_normalised_and_deduped(self) -> None:
        m = ReticulumUpdate(**_REQUIRED, telemetry_collector=(
            f"<{'ab' * 16}>\n{'CD' * 16}, {'ab' * 16}"
        ))
        self.assertEqual(m.telemetry_collector, "ab" * 16 + "\n" + "cd" * 16)

    def test_one_bad_line_rejects_the_lot(self) -> None:
        with self.assertRaises(ValidationError):
            ReticulumUpdate(**_REQUIRED, telemetry_collector=f"{'ab' * 16}\nnope")

    def test_interval_floor(self) -> None:
        with self.assertRaises(ValidationError):
            ReticulumUpdate(**_REQUIRED, telemetry_interval_s=60)

    def test_include_location_defaults_off_and_round_trips(self) -> None:
        self.assertFalse(ReticulumUpdate(**_REQUIRED).telemetry_include_location)
        m = ReticulumUpdate(**_REQUIRED, telemetry_include_location=True)
        self.assertTrue(m.telemetry_include_location)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
