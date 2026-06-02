"""Tests for SX1302Wrapper SPI preflight, SX1261 carrier guard, and model ID."""

from __future__ import annotations

import ctypes
import unittest
from unittest.mock import MagicMock, patch

from src.hal.sx1302_types import (
    SX1302_MODEL_ID_SX1302,
    SX1302_MODEL_ID_SX1303,
)
from src.hal.sx1302_wrapper import LGW_HAL_SUCCESS, SX1302Wrapper


def _build_wrapper() -> SX1302Wrapper:
    wrapper = SX1302Wrapper(sx1261_spi_path="/dev/spidev0.1")
    wrapper._lib = MagicMock()
    return wrapper


class TestSx1261CarrierGuard(unittest.TestCase):
    def test_rak_carrier_clears_non_empty_sx1261_path(self) -> None:
        wrapper = _build_wrapper()
        wrapper.set_carrier_type("rak")
        wrapper._guard_sx1261_spi_path()
        self.assertEqual(wrapper._sx1261_spi_path, "")

    def test_sensecap_carrier_clears_non_empty_sx1261_path(self) -> None:
        wrapper = _build_wrapper()
        wrapper.set_carrier_type("sensecap_m1")
        wrapper._guard_sx1261_spi_path()
        self.assertEqual(wrapper._sx1261_spi_path, "")

    def test_unknown_carrier_keeps_sx1261_path(self) -> None:
        wrapper = _build_wrapper()
        wrapper.set_carrier_type("")
        wrapper._guard_sx1261_spi_path()
        self.assertEqual(wrapper._sx1261_spi_path, "/dev/spidev0.1")

    def test_empty_sx1261_path_unchanged_on_rak(self) -> None:
        wrapper = SX1302Wrapper(sx1261_spi_path="")
        wrapper.set_carrier_type("rak")
        wrapper._guard_sx1261_spi_path()
        self.assertEqual(wrapper._sx1261_spi_path, "")


class TestSpiPreflight(unittest.TestCase):
    def test_missing_spi_device_raises(self) -> None:
        wrapper = SX1302Wrapper(spi_path="/dev/spidev0.0")
        with patch("src.hal.sx1302_wrapper.os.path.exists", return_value=False):
            with self.assertRaises(FileNotFoundError) as ctx:
                wrapper._preflight_spi()
        self.assertIn("raspi-config", str(ctx.exception))


class TestConcentratorModelId(unittest.TestCase):
    def test_model_label_sx1303(self) -> None:
        wrapper = SX1302Wrapper()
        wrapper._concentrator_model_id = SX1302_MODEL_ID_SX1303
        self.assertEqual(wrapper.concentrator_model_label, "SX1303")

    def test_model_label_sx1302(self) -> None:
        wrapper = SX1302Wrapper()
        wrapper._concentrator_model_id = SX1302_MODEL_ID_SX1302
        self.assertEqual(wrapper.concentrator_model_label, "SX1302")

    def test_read_model_id_from_hal(self) -> None:
        wrapper = _build_wrapper()

        def fake_get_model(model_ptr):
            ptr = ctypes.cast(model_ptr, ctypes.POINTER(ctypes.c_uint8))
            ptr[0] = SX1302_MODEL_ID_SX1303
            return LGW_HAL_SUCCESS

        wrapper._lib.sx1302_get_model_id.side_effect = fake_get_model
        wrapper._read_concentrator_model_id()
        self.assertEqual(wrapper._concentrator_model_id, SX1302_MODEL_ID_SX1303)


class TestSx1261ConfigureSkipsWhenPathCleared(unittest.TestCase):
    def test_configure_sx1261_skips_after_rak_guard(self) -> None:
        wrapper = _build_wrapper()
        wrapper.set_carrier_type("rak")
        wrapper._guard_sx1261_spi_path()
        wrapper._configure_sx1261_for_spectral_scan()
        wrapper._lib.lgw_sx1261_setconf.assert_not_called()


if __name__ == "__main__":
    unittest.main()
