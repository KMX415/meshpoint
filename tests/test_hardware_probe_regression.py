"""Regression coverage for safe fresh-install hardware detection."""
import subprocess
import unittest
from contextlib import ExitStack
from types import SimpleNamespace
from unittest.mock import patch
from src.cli import hardware_probe as probe
from src.cli import hardware_detect as detect


def result(output='', code=0):
    return SimpleNamespace(returncode=code, stdout=output, stderr='')


class ProbeTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(probe.os.path, 'isfile', return_value=True))
        self.stack.enter_context(patch.object(probe.Path, 'is_file', return_value=True))
        self.run = self.stack.enter_context(patch.object(probe.subprocess, 'run'))
        self.run.side_effect = [result('inactive'), result(), result('Note: chip version is 0x10 (v1.0)'), result()]

    def test_idle_rak_uses_absolute_reset_helper_and_version_only_child(self):
        self.assertEqual(probe.probe_concentrator_chip(), 'sx1302')
        commands = [c.args[0] for c in self.run.call_args_list]
        self.assertEqual(commands[1][:2], ['bash', '-e'])
        self.assertTrue(probe.Path(commands[1][2]).is_absolute())
        self.assertEqual(commands[3], commands[1] + ['--hold'])
        self.assertIn('hal.lgw_connect(0,', commands[2][2])
        self.assertNotIn('lgw_start(', commands[2][2])
        self.assertNotIn('lgw_send(', commands[2][2])

    def test_sx1303(self):
        self.run.side_effect = [result('inactive'), result(), result('Note: chip version is 0x12 (v1.2)'), result()]
        self.assertEqual(probe.probe_concentrator_chip(), 'sx1303')

    def test_running_or_unknown_service_never_resets(self):
        for state in ['active', 'activating', 'deactivating', '']:
            with self.subTest(state=state):
                self.run.reset_mock()
                self.run.side_effect = [result(state)]
                with self.assertRaisesRegex(probe.HardwareProbeError, 'Stop meshpoint'):
                    probe.probe_concentrator_chip()
                self.assertEqual(self.run.call_count, 1)

    def test_reset_failure_never_reads_hal(self):
        self.run.side_effect = [result('inactive'), result(code=1), result()]
        with self.assertRaisesRegex(probe.HardwareProbeError, 'reset failed'):
            probe.probe_concentrator_chip()
        self.assertEqual(self.run.call_count, 3)
        self.assertEqual(self.run.call_args.args[0][-1], '--hold')

    def test_timeout_still_holds_reset(self):
        self.run.side_effect = [result('inactive'), result(), subprocess.TimeoutExpired('probe',10), result()]
        with self.assertRaises(probe.HardwareProbeError):
            probe.probe_concentrator_chip()
        self.assertEqual(self.run.call_args.args[0][-1], '--hold')

    def test_hal_error_is_not_accepted_even_with_version(self):
        self.run.side_effect = [result('inactive'), result(), result('chip version is 0x10',1), result()]
        with self.assertRaisesRegex(probe.HardwareProbeError, 'version read failed'):
            probe.probe_concentrator_chip()

    def test_unrecognized_or_unrelated_hex_is_not_a_chip(self):
        for output in ['EUI: 0x10abcdef12345678', 'address 0x12', 'chip version is 0x00', 'chip version is 0xFF', 'chip version is 0x1000']:
            with self.subTest(output=output):
                self.assertIsNone(probe._parse_chip_version(output))
                self.run.side_effect = [result('inactive'), result(), result(output), result()]
                with self.assertRaises(probe.HardwareProbeError):
                    probe.probe_concentrator_chip()

    def test_missing_library_does_not_reset(self):
        with patch.object(probe.os.path, 'isfile', return_value=False):
            with self.assertRaisesRegex(probe.HardwareProbeError, 'HAL library missing'):
                probe.probe_concentrator_chip()
        self.run.assert_not_called()

    def test_missing_helper_does_not_reset(self):
        with patch.object(probe.Path, 'is_file', return_value=False):
            with self.assertRaisesRegex(probe.HardwareProbeError, 'helper missing'):
                probe.probe_concentrator_chip()
        self.run.assert_not_called()


class BoardSelectionTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        for name, value in [('detect_spi_devices', ['/dev/spidev0.0']), ('detect_serial_ports', []),
                            ('detect_meshcore_usb_candidates', []), ('check_libloragw', True),
                            ('detect_carrier_board','rak'), ('probe_gps', detect.GpsProbeResult())]:
            self.stack.enter_context(patch.object(detect, name, return_value=value))
        self.hat = self.stack.enter_context(patch.object(detect, 'detect_wismesh_hat', return_value=False))
        self.provision = self.stack.enter_context(patch('src.radio.pimesh_supervisor.read_json', return_value={}))
        self.probe = self.stack.enter_context(patch.object(detect, 'probe_concentrator_chip', return_value='sx1302'))

    def test_rak_selected_from_confirmed_chip(self):
        r=detect.detect_all()
        self.assertTrue(r.concentrator_available)
        self.assertEqual(r.platform,'gateway')

    def test_wismesh_never_runs_gateway_probe(self):
        self.hat.return_value=True
        r=detect.detect_all()
        self.assertEqual(r.platform,'node')
        self.probe.assert_not_called()

    def test_provisioned_pimesh_never_runs_gateway_probe(self):
        for board in ['pimesh-v1','pimesh-v2']:
            self.provision.return_value={'board':board}
            r=detect.detect_all()
            self.assertFalse(r.concentrator_available)
        self.probe.assert_not_called()

    def test_probe_failure_is_preserved_for_setup(self):
        self.probe.side_effect=probe.HardwareProbeError('reset failed')
        r=detect.detect_all()
        self.assertEqual(r.concentrator_error,'reset failed')
        self.assertFalse(r.concentrator_available)