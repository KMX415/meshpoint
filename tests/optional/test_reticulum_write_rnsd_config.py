"""write_rnsd_config.py -- the extra-interface INI block builder.

Pure string generation; `load_config` is deferred into main() so this
imports on the dev Mac.
"""

from __future__ import annotations

import unittest
from apps.reticulum.backend import rns_config as w


class TestExtraInterfaceBlocks(unittest.TestCase):
    def test_tcp_client_block(self) -> None:
        out = w._extra_interface_blocks([
            {"name": "Second backbone", "type": "TCPClientInterface",
             "enabled": True, "target_host": "node.example.com", "target_port": 4242},
        ])
        self.assertIn("[[Second backbone]]", out)
        self.assertIn("type = TCPClientInterface", out)
        self.assertIn("target_host = node.example.com", out)
        self.assertIn("target_port = 4242", out)
        self.assertIn("enabled = Yes", out)

    def test_udp_block_has_all_four_fields(self) -> None:
        out = w._extra_interface_blocks([
            {"name": "LAN", "type": "UDPInterface", "listen_ip": "0.0.0.0",
             "listen_port": 4242, "forward_ip": "255.255.255.255", "forward_port": 4242},
        ])
        for f in ("listen_ip", "listen_port", "forward_ip", "forward_port"):
            self.assertIn(f + " = ", out)

    def test_disabled_entry_is_skipped(self) -> None:
        out = w._extra_interface_blocks([
            {"name": "Off", "type": "TCPClientInterface", "enabled": False,
             "target_host": "x", "target_port": 1},
        ])
        self.assertEqual(out, "")

    def test_unknown_type_reserved_dup_and_missing_field_all_skipped(self) -> None:
        out = w._extra_interface_blocks([
            {"name": "A", "type": "Nope"},
            {"name": "RNode LoRa", "type": "TCPClientInterface", "target_host": "x", "target_port": 1},
            {"name": "Dup", "type": "TCPClientInterface", "target_host": "x", "target_port": 1},
            {"name": "Dup", "type": "TCPClientInterface", "target_host": "y", "target_port": 2},
            {"name": "NoPort", "type": "TCPServerInterface", "listen_ip": "0.0.0.0"},
        ])
        self.assertEqual(out.count("[["), 1)  # only the first "Dup" survives
        self.assertIn("[[Dup]]", out)
        self.assertNotIn("RNode LoRa", out)

    def test_bracket_stripped_from_name(self) -> None:
        out = w._extra_interface_blocks([
            {"name": "[[weird]]", "type": "TCPClientInterface",
             "target_host": "x", "target_port": 1},
        ])
        self.assertIn("[[weird]]", out)
        self.assertNotIn("[[[[", out)

    def test_non_list_input_is_empty(self) -> None:
        self.assertEqual(w._extra_interface_blocks(None), "")
        self.assertEqual(w._extra_interface_blocks("nope"), "")
        self.assertEqual(w._extra_interface_blocks([]), "")

    def test_template_has_the_extra_slot(self) -> None:
        # a formatting regression here means rnsd gets a broken config
        rendered = w._TEMPLATE.format(rnode_block="", backbone_block="", extra_block="X")
        self.assertIn("X", rendered)
        self.assertIn("[interfaces]", rendered)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
