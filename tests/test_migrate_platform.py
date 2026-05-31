"""Tests for migrate-platform CLI."""

import unittest
from argparse import Namespace
from unittest.mock import patch

from src.cli.hardware_detect import HardwareReport, PLATFORM_GATEWAY, PLATFORM_NODE
from src.cli.migrate_platform_command import run_migrate_platform


class TestMigratePlatform(unittest.TestCase):
    @patch("src.cli.migrate_platform_command.save_section_to_yaml")
    @patch("src.cli.migrate_platform_command.detect_all")
    def test_migrate_to_node_updates_yaml(self, mock_detect, mock_save):
        mock_detect.return_value = HardwareReport(
            wismesh_hat_detected=True,
            platform=PLATFORM_NODE,
            hardware_description="WisMesh Pi HAT (RAK6421)",
        )
        args = Namespace(to="node", force=False, restart=False)
        code = run_migrate_platform(args)
        self.assertEqual(code, 0)
        mock_save.assert_any_call("device", {"platform": "node"})
        mock_save.assert_any_call("capture", {"sources": ["meshtasticd"]})

    @patch("src.cli.migrate_platform_command.save_section_to_yaml")
    @patch("src.cli.migrate_platform_command.detect_all")
    def test_migrate_to_gateway_requires_concentrator(self, mock_detect, mock_save):
        mock_detect.return_value = HardwareReport(
            concentrator_available=False,
            wismesh_hat_detected=True,
            platform=PLATFORM_NODE,
        )
        args = Namespace(to="gateway", force=False, restart=False)
        code = run_migrate_platform(args)
        self.assertEqual(code, 1)
        mock_save.assert_not_called()

    @patch("src.cli.migrate_platform_command.save_section_to_yaml")
    @patch("src.cli.migrate_platform_command.detect_all")
    def test_migrate_to_gateway_force(self, mock_detect, mock_save):
        mock_detect.return_value = HardwareReport(concentrator_available=False)
        args = Namespace(to="gateway", force=True, restart=False)
        code = run_migrate_platform(args)
        self.assertEqual(code, 0)
        mock_save.assert_any_call("device", {"platform": "gateway"})


if __name__ == "__main__":
    unittest.main()
