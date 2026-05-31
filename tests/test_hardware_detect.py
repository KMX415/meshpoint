"""Tests for concentrator chip probe and WisMesh HAT detection."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from src.cli.hardware_detect import (
    CARRIER_WISMESH,
    PLATFORM_GATEWAY,
    PLATFORM_NODE,
    detect_all,
)
from src.cli.hardware_probe import (
    _parse_chip_version,
    detect_wismesh_hat,
    probe_concentrator_chip,
)


class TestParseChipVersion(unittest.TestCase):

    def test_sx1302(self):
        self.assertEqual(
            _parse_chip_version("INFO: Concentrator version: 0x10\n"),
            "sx1302",
        )

    def test_sx1303(self):
        self.assertEqual(
            _parse_chip_version("Chip version is 0x12"),
            "sx1303",
        )

    def test_garbage_version_ignored(self):
        self.assertIsNone(_parse_chip_version("Chip version is 0x00"))

    def test_no_match(self):
        self.assertIsNone(_parse_chip_version("no version here"))


class TestProbeConcentratorChip(unittest.TestCase):

    @patch("src.cli.hardware_probe._find_chip_id_binary", return_value=None)
    def test_missing_binary_returns_none(self, _mock_find):
        self.assertIsNone(probe_concentrator_chip())

    @patch("src.cli.hardware_probe.subprocess.run")
    @patch("src.cli.hardware_probe._find_chip_id_binary", return_value="/opt/chip_id")
    def test_parses_sx1302_output(self, _mock_find, mock_run):
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = "version 0x10"
        mock_run.return_value.stderr = ""
        self.assertEqual(probe_concentrator_chip("/dev/spidev0.0"), "sx1302")
        mock_run.assert_called_once()


class TestDetectWismeshHat(unittest.TestCase):

    @patch(
        "src.cli.hardware_probe._read_device_tree_string",
        side_effect=lambda path: {
            "/proc/device-tree/hat/product": "RAK6421 WisMesh Pi HAT",
            "/proc/device-tree/hat/vendor": "RAKwireless",
        }.get(path),
    )
    def test_detects_rak6421_product(self, _mock_read):
        self.assertTrue(detect_wismesh_hat())

    @patch(
        "src.cli.hardware_probe._read_device_tree_string",
        return_value=None,
    )
    def test_missing_hat_tree(self, _mock_read):
        self.assertFalse(detect_wismesh_hat())


class TestDetectAllPlatform(unittest.TestCase):

    @patch("src.cli.hardware_detect.probe_gps")
    @patch("src.cli.hardware_detect.detect_carrier_board", return_value="rak")
    @patch("src.cli.hardware_detect.probe_concentrator_chip", return_value="sx1302")
    @patch("src.cli.hardware_detect.check_libloragw", return_value=True)
    @patch("src.cli.hardware_detect.detect_wismesh_hat", return_value=False)
    @patch("src.cli.hardware_detect.detect_spi_devices", return_value=["/dev/spidev0.0"])
    @patch("src.cli.hardware_detect.detect_serial_ports", return_value=[])
    @patch("src.cli.hardware_detect.detect_meshcore_usb_candidates", return_value=[])
    def test_gateway_when_chip_responds(
        self,
        *_mocks,
    ):
        report = detect_all()
        self.assertEqual(report.platform, PLATFORM_GATEWAY)
        self.assertTrue(report.concentrator_available)
        self.assertEqual(report.concentrator_chip, "sx1302")

    @patch("src.cli.hardware_detect.probe_gps")
    @patch("src.cli.hardware_detect.detect_carrier_board", return_value="rak")
    @patch("src.cli.hardware_detect.probe_concentrator_chip", return_value=None)
    @patch("src.cli.hardware_detect.check_libloragw", return_value=True)
    @patch("src.cli.hardware_detect.detect_wismesh_hat", return_value=True)
    @patch("src.cli.hardware_detect.detect_spi_devices", return_value=["/dev/spidev0.0"])
    @patch("src.cli.hardware_detect.detect_serial_ports", return_value=[])
    @patch("src.cli.hardware_detect.detect_meshcore_usb_candidates", return_value=[])
    def test_node_when_wismesh_and_no_chip(
        self,
        *_mocks,
    ):
        report = detect_all()
        self.assertEqual(report.platform, PLATFORM_NODE)
        self.assertFalse(report.concentrator_available)
        self.assertTrue(report.wismesh_hat_detected)
        self.assertEqual(report.carrier_type, CARRIER_WISMESH)
