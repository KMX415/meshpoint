"""Tests for HAL GPS/PPS ctypes bindings and wrapper integration."""

from __future__ import annotations

import ctypes
import unittest
from unittest.mock import MagicMock, patch

from src.config import AppConfig, LocationConfig, RadioConfig, validate_config_consistency
from src.hal.sx1302_gps import HalGpsPpsSync
from src.hal.sx1302_gps_types import GPS_MSG_UBX_NAV_TIMEGPS, LGW_GPS_SUCCESS
from src.hal.sx1302_wrapper import LGW_HAL_SUCCESS, SX1302Wrapper


def _mock_lib_with_gps() -> MagicMock:
    lib = MagicMock()
    lib.lgw_gps_enable = MagicMock(return_value=LGW_GPS_SUCCESS)
    lib.lgw_gps_disable = MagicMock(return_value=LGW_GPS_SUCCESS)
    lib.lgw_parse_nmea = MagicMock(return_value=0)
    lib.lgw_parse_ubx = MagicMock(return_value=0)
    lib.lgw_gps_get = MagicMock(return_value=LGW_GPS_SUCCESS)
    lib.lgw_get_trigcnt = MagicMock(return_value=LGW_HAL_SUCCESS)
    lib.lgw_gps_sync = MagicMock(return_value=LGW_GPS_SUCCESS)
    lib.sx1302_gps_enable = MagicMock(return_value=LGW_HAL_SUCCESS)
    return lib


class TestConfigGpsConflict(unittest.TestCase):
    def test_uart_and_pps_same_tty_raises(self) -> None:
        cfg = AppConfig(
            radio=RadioConfig(gps_pps_enabled=True, gps_pps_tty_path="/dev/ttyAMA0"),
            location=LocationConfig(source="uart", uart_path="/dev/ttyAMA0"),
        )
        with self.assertRaises(ValueError) as ctx:
            validate_config_consistency(cfg)
        self.assertIn("cannot share", str(ctx.exception))

    def test_uart_and_pps_different_tty_ok(self) -> None:
        cfg = AppConfig(
            radio=RadioConfig(
                gps_pps_enabled=True, gps_pps_tty_path="/dev/ttyAMA0"
            ),
            location=LocationConfig(source="uart", uart_path="/dev/ttyUSB0"),
        )
        validate_config_consistency(cfg)

    def test_pps_with_gpsd_ok(self) -> None:
        cfg = AppConfig(
            radio=RadioConfig(
                gps_pps_enabled=True, gps_pps_tty_path="/dev/ttyAMA0"
            ),
            location=LocationConfig(source="gpsd"),
        )
        validate_config_consistency(cfg)


class TestHalGpsPpsSync(unittest.TestCase):
    def test_unsupported_lib_returns_false(self) -> None:
        lib = MagicMock(spec=[])
        sync = HalGpsPpsSync(lib)
        self.assertFalse(sync.start())
        self.assertIn("lgw_gps_enable", sync.get_status().last_error or "")

    @patch("src.hal.sx1302_gps.os.read", return_value=b"")
    def test_start_enables_hal_and_sx1302_pps(self, _read: MagicMock) -> None:
        lib = _mock_lib_with_gps()
        fd_holder = {"value": 7}

        def fake_enable(path, family, baud, fd_ptr):
            ctypes.cast(fd_ptr, ctypes.POINTER(ctypes.c_int))[0] = fd_holder["value"]
            return LGW_GPS_SUCCESS

        lib.lgw_gps_enable.side_effect = fake_enable

        sync = HalGpsPpsSync(lib, tty_path="/dev/ttyAMA0", gps_family="ubx7")
        self.assertTrue(sync.start())
        lib.sx1302_gps_enable.assert_called_once_with(True)
        status = sync.get_status()
        self.assertTrue(status.enabled)
        self.assertTrue(status.available)
        sync.stop()
        lib.lgw_gps_disable.assert_called_once_with(7)
        lib.sx1302_gps_enable.assert_called_with(False)

    def test_ubx_nav_timegps_triggers_sync(self) -> None:
        lib = _mock_lib_with_gps()
        lib.lgw_parse_ubx.return_value = GPS_MSG_UBX_NAV_TIMEGPS

        sync = HalGpsPpsSync(lib)
        sync._enabled = True
        sync._fd = 1
        sync._consume_parse_buffer(bytearray(b"\xb5\x62"))
        lib.lgw_gps_sync.assert_called_once()
        self.assertTrue(sync.get_status().last_sync_ok)


class TestWrapperGpsPps(unittest.TestCase):
    def test_start_gps_pps_after_concentrator_start(self) -> None:
        wrapper = SX1302Wrapper()
        wrapper._lib = _mock_lib_with_gps()
        wrapper._started = True

        def fake_enable(path, family, baud, fd_ptr):
            ctypes.cast(fd_ptr, ctypes.POINTER(ctypes.c_int))[0] = 3
            return LGW_GPS_SUCCESS

        wrapper._lib.lgw_gps_enable.side_effect = fake_enable

        with patch("src.hal.sx1302_gps.os.read", return_value=b""):
            self.assertTrue(
                wrapper.start_gps_pps(
                    tty_path="/dev/ttyAMA0",
                    gps_family="ubx7",
                )
            )
        self.assertIsNotNone(wrapper.gps_pps)
        wrapper.stop_gps_pps()
