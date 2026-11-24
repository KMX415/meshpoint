"""Regression fence: gateway concentrator work must not break WisMesh Node.

Run after every ``git merge origin/main`` into ``feat/wismesh-hat``.
See docs/plans/wismesh-branch-merge.md.
"""

import unittest
from unittest.mock import MagicMock, patch

from src.api.server import (
    _bootstrap_pki,
    _build_pipeline,
    _build_position_broadcaster,
    _build_spectral_scan_service,
    _build_telemetry_broadcaster,
    _hydrate_public_keys,
    _setup_inbound_responder,
    _wire_native_relay,
)
from src.config import AppConfig, CaptureConfig, DeviceConfig, MeshtasticdConfig, TransmitConfig
from src.platform_guards import GATEWAY_ONLY_CAPABILITIES, is_node_platform


def _node_config() -> AppConfig:
    cfg = AppConfig()
    cfg.device = DeviceConfig(platform="node")
    cfg.capture = CaptureConfig(
        sources=["meshtasticd"],
        meshtasticd=MeshtasticdConfig(host="127.0.0.1", port=4403),
    )
    cfg.transmit = TransmitConfig(enabled=False)
    return cfg


class TestPlatformGuardRegistry(unittest.TestCase):
    def test_registry_documents_gateway_only_surface(self):
        expected = {
            "pki_keypair_bootstrap",
            "pki_public_key_hydration",
            "inbound_mesh_participant_replies",
            "telemetry_broadcaster",
            "position_broadcaster",
            "tx_gain_injection",
            "native_sx1302_relay",
            "spectral_scan",
            "concentrator_dangerous_action",
        }
        self.assertEqual(set(GATEWAY_ONLY_CAPABILITIES), expected)


class TestNodePipelineShape(unittest.TestCase):
    def test_node_pipeline_uses_meshtasticd_not_concentrator(self):
        cfg = _node_config()
        with patch("src.api.server._add_meshtasticd_source") as add_md:
            with patch("src.api.server._add_concentrator_source") as add_conc:
                with patch("src.api.server.PipelineCoordinator") as mock_pc:
                    mock_pc.return_value = MagicMock()
                    _build_pipeline(cfg)
        add_md.assert_called_once()
        add_conc.assert_not_called()

    def test_node_skips_meshcore_usb_autodetect(self):
        cfg = _node_config()
        cfg.capture.meshcore_usb.auto_detect = True
        with patch("src.api.server._add_meshcore_usb_source") as add_mc:
            with patch("src.api.server.PipelineCoordinator") as mock_pc:
                mock_pc.return_value = MagicMock()
                _build_pipeline(cfg)
        add_mc.assert_not_called()


class TestGatewayOnlyCapabilitiesOnNode(unittest.IsolatedAsyncioTestCase):
    async def test_pki_bootstrap_noop(self):
        coord = MagicMock()
        coord._crypto = MagicMock()
        with patch("src.identity.keypair.KeypairStore") as store:
            _bootstrap_pki(_node_config(), coord)
            store.assert_not_called()

    async def test_hydrate_public_keys_noop(self):
        coord = MagicMock()
        coord._crypto = MagicMock()
        await _hydrate_public_keys(coord, _node_config())
        coord.database.connect.assert_not_called()

    def test_inbound_responder_noop(self):
        coord = MagicMock()
        tx = MagicMock(meshtastic_enabled=True, source_node_id=0xAABBCCDD)
        _setup_inbound_responder(coord, tx, _node_config())
        coord.on_packet.assert_not_called()

    def test_broadcasters_none(self):
        tx = MagicMock(meshtastic_enabled=True)
        coord = MagicMock()
        cfg = _node_config()
        self.assertIsNone(_build_telemetry_broadcaster(cfg, tx, coord))
        self.assertIsNone(_build_position_broadcaster(cfg, tx, coord))

    def test_spectral_scan_none_even_when_enabled(self):
        cfg = _node_config()
        cfg.radio.spectral_scan_interval_seconds = 60.0
        coord = MagicMock()
        self.assertIsNone(
            _build_spectral_scan_service(coord, cfg, MagicMock())
        )

    def test_lifespan_skips_tx_gain_on_node(self):
        cfg = _node_config()
        cfg.transmit.enabled = True
        # Mirrors server.py lifespan guard before _inject_tx_gain_into_source.
        self.assertFalse(cfg.transmit.enabled and not is_node_platform(cfg))

    def test_native_relay_skipped_without_wrapper(self):
        coord = MagicMock()
        tx = MagicMock()
        with patch("src.api.server._get_concentrator_wrapper", return_value=None):
            _wire_native_relay(coord, tx)
        coord.relay_manager.set_transmit_function.assert_not_called()


class TestNodePlatformDetection(unittest.TestCase):
    def test_node_config_detected(self):
        self.assertTrue(is_node_platform(_node_config()))


if __name__ == "__main__":
    unittest.main()
