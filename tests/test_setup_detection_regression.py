"""Wizard must not overwrite capture settings after a probe failure."""
import unittest
from unittest.mock import patch
from types import SimpleNamespace
from src.cli import setup_wizard as wizard
from src.cli.hardware_detect import HardwareReport

class WizardDetectionTests(unittest.TestCase):
    @patch.object(wizard, '_is_systemd', return_value=False)
    @patch.object(wizard, 'print_report')
    @patch.object(wizard, 'detect_all', return_value=HardwareReport(concentrator_error='probe failed'))
    @patch.object(wizard, '_step_region')
    @patch.object(wizard, '_write_config')
    @patch.object(wizard, '_preflight_check')
    @patch.object(wizard, '_load_existing_config', return_value={})
    def test_failure_stops_before_configuration(self, load, preflight, write, region, detect, report, systemd):
        with self.assertRaises(SystemExit):
            wizard.run_setup()
        write.assert_not_called()
        region.assert_not_called()

    @patch.object(wizard, '_is_systemd', return_value=True)
    @patch.object(wizard, 'detect_all')
    @patch.object(wizard, '_confirm', return_value=False)
    @patch.object(wizard.subprocess, 'run', return_value=SimpleNamespace(returncode=0, stdout='active'))
    def test_declining_stop_never_probes(self, run, confirm, detect, systemd):
        with self.assertRaises(SystemExit):
            wizard._step_hardware_detect()
        detect.assert_not_called()
        self.assertEqual(run.call_count,1)

    @patch.object(wizard, '_is_systemd', return_value=True)
    @patch.object(wizard, 'print_report')
    @patch.object(wizard, 'detect_all', return_value=HardwareReport(concentrator_available=True, concentrator_chip='sx1302'))
    @patch.object(wizard, '_confirm', return_value=True)
    @patch.object(wizard.subprocess, 'run', side_effect=[SimpleNamespace(returncode=0, stdout='active'), SimpleNamespace(returncode=0)])
    def test_approved_stop_precedes_detection(self, run, confirm, detect, report, systemd):
        self.assertTrue(wizard._step_hardware_detect().concentrator_available)
        self.assertEqual(run.call_args.args[0], ['sudo','systemctl','stop','meshpoint'])
        detect.assert_called_once()

    @patch('src.radio.pimesh_supervisor.read_json')
    def test_pimesh_protocol_selection_unchanged(self, read):
        for board in ['pimesh-v1','pimesh-v2']:
            for protocol, source in [('meshtastic','meshtasticd'),('meshcore','meshcore_usb')]:
                read.side_effect=[{'board':board},{'active':protocol}]
                config={}
                wizard._step_capture_source(config, HardwareReport())
                self.assertEqual(config['capture']['sources'],[source])
                self.assertEqual(config['device']['radio_hat'],board)

    @patch('src.radio.pimesh_supervisor.read_json', return_value={})
    @patch.object(wizard, '_maybe_add_meshcore_usb')
    def test_rak_and_wismesh_capture_selection(self, usb, read):
        for report, source in [(HardwareReport(concentrator_available=True, spi_devices=['/dev/spidev0.0']), 'concentrator'),
                               (HardwareReport(platform='node',wismesh_hat_detected=True), 'meshtasticd')]:
            config={}
            wizard._step_capture_source(config, report)
            self.assertEqual(config['capture']['sources'],[source])