"""Regression coverage for #179 on an existing, unmodified HAL installation."""
import ctypes
from unittest.mock import MagicMock, patch

import pytest

from src.hal.concentrator_config import ChannelConfig, ConcentratorChannelPlan
from src.hal.sx1302_wrapper import SX1302Wrapper


def wrapper(enabled=True):
    w = SX1302Wrapper()
    lib = MagicMock()
    registers = {}
    def start():
        registers.update({916: 8, 917: 0})
        return 0
    def write(reg, value):
        registers[reg] = value
        return 0
    def read(reg, ptr):
        ctypes.cast(ptr, ctypes.POINTER(ctypes.c_int32))[0] = registers[reg]
        return 0
    lib.lgw_start.side_effect = start
    lib.lgw_reg_w.side_effect = write
    lib.lgw_reg_r.side_effect = read
    w._lib = lib
    w._service_modem_enabled = enabled
    return w, lib, registers


def test_existing_hal_start_and_restart_restore_rx_only_setting():
    w, lib, registers = wrapper()
    for _ in range(2):
        w.start()
        assert w._started
        assert registers == {916: 16, 917: 0}
        w.stop()
    assert [call.args for call in lib.lgw_reg_w.call_args_list] == [(916, 16), (917, 0)] * 2
    assert lib.lgw_reg_w.argtypes == [ctypes.c_uint16, ctypes.c_int32]
    lib.lgw_send.assert_not_called()
    lib.lgw_txgain_setconf.assert_not_called()


@pytest.mark.parametrize('channel', [None, ChannelConfig(frequency_hz=906875000, enabled=False)])
def test_disabled_service_modem_is_untouched(channel):
    w, lib, _ = wrapper()
    plan = ConcentratorChannelPlan()
    plan.single_sf_channel = channel
    with patch.object(w, '_configure_board'), patch.object(w, '_configure_rf_chains'), patch.object(w, '_configure_if_channels'), patch.object(w, '_configure_sx1261_for_spectral_scan'):
        w.configure(plan)
    w.start()
    lib.lgw_reg_w.assert_not_called()
    lib.lgw_reg_r.assert_not_called()


@pytest.mark.parametrize('failure', ['write', 'read', 'mismatch', 'missing'])
def test_failed_setting_stops_hal_and_does_not_report_started(failure):
    w, lib, _ = wrapper()
    if failure == 'write':
        lib.lgw_reg_w.side_effect = None
        lib.lgw_reg_w.return_value = -1
    elif failure == 'read':
        lib.lgw_reg_r.side_effect = None
        lib.lgw_reg_r.return_value = -1
    elif failure == 'mismatch':
        lib.lgw_reg_r.side_effect = None
        lib.lgw_reg_r.return_value = 0
    else:
        del lib.lgw_reg_w
    with pytest.raises(RuntimeError):
        w.start()
    assert not w._started
    lib.lgw_stop.assert_called_once()


def test_failed_hal_start_never_accesses_registers():
    w, lib, _ = wrapper()
    lib.lgw_start.side_effect = None
    lib.lgw_start.return_value = -1
    with pytest.raises(RuntimeError):
        w.start()
    lib.lgw_reg_w.assert_not_called()
    assert not w._started


def test_configured_service_channel_enables_override():
    w, lib, registers = wrapper(enabled=False)
    plan = ConcentratorChannelPlan()
    plan.single_sf_channel = ChannelConfig(frequency_hz=906875000)
    with patch.object(w, '_configure_board'), patch.object(w, '_configure_rf_chains'), patch.object(w, '_configure_if_channels'), patch.object(w, '_configure_sx1261_for_spectral_scan'):
        w.configure(plan)
    w.start()
    assert registers == {916: 16, 917: 0}
    calls = [call[0] for call in lib.mock_calls]
    assert calls.index('lgw_start') < calls.index('lgw_reg_w') < calls.index('lgw_reg_r')
