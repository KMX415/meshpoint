"""Tests for USB serial port classification by USB VID/PID."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from src.hal.usb_classifier import (
    PortClass,
    PortInfo,
    UsbPortClassifier,
    should_skip_for_meshcore_probe,
)


def _make_comport_entry(
    device: str,
    vid: int | None = None,
    pid: int | None = None,
    manufacturer: str | None = None,
    product: str | None = None,
) -> MagicMock:
    entry = MagicMock()
    entry.device = device
    entry.vid = vid
    entry.pid = pid
    entry.manufacturer = manufacturer
    entry.product = product
    return entry


class TestClassifyByVid(unittest.TestCase):
    """Bare ``classify`` returns the right ``PortClass`` for known VIDs."""

    def setUp(self) -> None:
        self.classifier = UsbPortClassifier()

    def test_ublox_vid_classifies_as_gps_known(self) -> None:
        self.assertEqual(self.classifier.classify(0x1546), PortClass.GPS_KNOWN)

    def test_unknown_vid_returns_unknown(self) -> None:
        self.assertEqual(self.classifier.classify(0xDEAD), PortClass.UNKNOWN)

    def test_silabs_cp210x_is_intentionally_unknown(self) -> None:
        # CP210x is shared between concentrator and Heltec MeshCore companion;
        # we keep it ambiguous so the existing handshake probe disambiguates.
        self.assertEqual(self.classifier.classify(0x10C4), PortClass.UNKNOWN)

    def test_none_vid_returns_unknown(self) -> None:
        self.assertEqual(self.classifier.classify(None), PortClass.UNKNOWN)


class TestListPorts(unittest.TestCase):
    """``list_ports`` enriches pyserial output with classification."""

    def test_ublox_7_recognized_as_gps(self) -> None:
        entries = [
            _make_comport_entry(
                "/dev/ttyACM0",
                vid=0x1546,
                pid=0x01A7,
                manufacturer="u-blox AG - www.u-blox.com",
                product="u-blox 7 - GPS/GNSS Receiver",
            ),
        ]
        with patch(
            "serial.tools.list_ports.comports", return_value=entries
        ):
            infos = UsbPortClassifier().list_ports()

        self.assertEqual(len(infos), 1)
        self.assertEqual(infos[0].device, "/dev/ttyACM0")
        self.assertEqual(infos[0].port_class, PortClass.GPS_KNOWN)
        self.assertEqual(infos[0].vid, 0x1546)
        self.assertEqual(infos[0].pid, 0x01A7)

    def test_ublox_8_recognized_as_gps(self) -> None:
        entries = [
            _make_comport_entry(
                "/dev/ttyACM0",
                vid=0x1546,
                pid=0x01A8,
                manufacturer="u-blox AG - www.u-blox.com",
                product="u-blox GNSS receiver",
            ),
        ]
        with patch(
            "serial.tools.list_ports.comports", return_value=entries
        ):
            infos = UsbPortClassifier().list_ports()

        self.assertEqual(infos[0].port_class, PortClass.GPS_KNOWN)

    def test_concentrator_cp2102_stays_unknown(self) -> None:
        entries = [
            _make_comport_entry(
                "/dev/ttyUSB0",
                vid=0x10C4,
                pid=0xEA60,
                manufacturer="Silicon Labs",
                product="CP2102 USB to UART Bridge Controller",
            ),
        ]
        with patch(
            "serial.tools.list_ports.comports", return_value=entries
        ):
            infos = UsbPortClassifier().list_ports()

        self.assertEqual(infos[0].port_class, PortClass.UNKNOWN)

    def test_mixed_ports_get_distinct_classes(self) -> None:
        entries = [
            _make_comport_entry(
                "/dev/ttyACM0", vid=0x1546, pid=0x01A7
            ),
            _make_comport_entry(
                "/dev/ttyUSB0", vid=0x10C4, pid=0xEA60
            ),
        ]
        with patch(
            "serial.tools.list_ports.comports", return_value=entries
        ):
            infos = {info.device: info for info in UsbPortClassifier().list_ports()}

        self.assertEqual(infos["/dev/ttyACM0"].port_class, PortClass.GPS_KNOWN)
        self.assertEqual(infos["/dev/ttyUSB0"].port_class, PortClass.UNKNOWN)

    def test_returns_empty_when_pyserial_missing(self) -> None:
        # Simulate a process where pyserial is unavailable. ``list_ports``
        # should return an empty list rather than raise.
        import builtins

        real_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "serial.tools" or name.startswith("serial.tools"):
                raise ImportError("simulated missing pyserial")
            return real_import(name, *args, **kwargs)

        with patch.object(builtins, "__import__", side_effect=fake_import):
            infos = UsbPortClassifier().list_ports()

        self.assertEqual(infos, [])


class TestKnownGpsDevices(unittest.TestCase):
    """``known_gps_devices`` filters down to ``GPS_KNOWN`` device paths."""

    def test_returns_only_gps_paths(self) -> None:
        entries = [
            _make_comport_entry("/dev/ttyACM0", vid=0x1546, pid=0x01A7),
            _make_comport_entry("/dev/ttyUSB0", vid=0x10C4, pid=0xEA60),
        ]
        with patch(
            "serial.tools.list_ports.comports", return_value=entries
        ):
            paths = UsbPortClassifier().known_gps_devices()

        self.assertEqual(paths, ["/dev/ttyACM0"])

    def test_no_gps_returns_empty(self) -> None:
        entries = [
            _make_comport_entry("/dev/ttyUSB0", vid=0x10C4, pid=0xEA60),
        ]
        with patch(
            "serial.tools.list_ports.comports", return_value=entries
        ):
            self.assertEqual(UsbPortClassifier().known_gps_devices(), [])


class TestShouldSkipForMeshcoreProbe(unittest.TestCase):
    """Convenience helper for ``meshcore_usb_detect.find_serial_candidates``."""

    def test_skips_known_gps_port(self) -> None:
        entries = [
            _make_comport_entry("/dev/ttyACM0", vid=0x1546, pid=0x01A7),
        ]
        with patch(
            "serial.tools.list_ports.comports", return_value=entries
        ):
            self.assertTrue(should_skip_for_meshcore_probe("/dev/ttyACM0"))

    def test_does_not_skip_unknown_port(self) -> None:
        entries = [
            _make_comport_entry("/dev/ttyUSB0", vid=0x10C4, pid=0xEA60),
        ]
        with patch(
            "serial.tools.list_ports.comports", return_value=entries
        ):
            self.assertFalse(should_skip_for_meshcore_probe("/dev/ttyUSB0"))

    def test_does_not_skip_port_not_in_enumeration(self) -> None:
        with patch(
            "serial.tools.list_ports.comports", return_value=[]
        ):
            self.assertFalse(should_skip_for_meshcore_probe("/dev/ttyACM0"))


class TestPortInfoDataclass(unittest.TestCase):
    """``PortInfo`` is the immutable carrier returned by ``list_ports``."""

    def test_port_info_is_frozen(self) -> None:
        info = PortInfo(
            device="/dev/ttyACM0",
            vid=0x1546,
            pid=0x01A7,
            manufacturer="u-blox AG",
            product="u-blox 7",
            port_class=PortClass.GPS_KNOWN,
        )
        with self.assertRaises(Exception):
            info.device = "/dev/ttyACM1"  # type: ignore[misc]


if __name__ == "__main__":
    unittest.main()
