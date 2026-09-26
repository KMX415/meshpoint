"""Gateway mesh-participant features must not run on WisMesh Node platform."""

import unittest
from unittest.mock import MagicMock, patch

from src.api.server import (
    _bootstrap_pki,
    _build_position_broadcaster,
    _build_telemetry_broadcaster,
    _hydrate_public_keys,
    _setup_inbound_responder,
)
from src.config import AppConfig, DeviceConfig, TransmitConfig


def _node_config() -> AppConfig:
    cfg = AppConfig()
    cfg.device = DeviceConfig(platform="node")
    cfg.transmit = TransmitConfig(enabled=False)
    return cfg


def _gateway_config() -> AppConfig:
    cfg = AppConfig()
    cfg.device = DeviceConfig(platform="gateway")
    cfg.transmit = TransmitConfig(enabled=True)
    return cfg


class TestNodePlatformMeshParticipantGuards(unittest.TestCase):
    def test_bootstrap_pki_skipped_on_node(self):
        coord = MagicMock()
        coord._crypto = MagicMock()
        with patch("src.identity.keypair.KeypairStore") as mock_store:
            _bootstrap_pki(_node_config(), coord)
            mock_store.assert_not_called()

    def test_hydrate_public_keys_skipped_on_node(self):
        import asyncio

        coord = MagicMock()
        coord._crypto = MagicMock()
        asyncio.run(_hydrate_public_keys(coord, _node_config()))
        coord.database.connect.assert_not_called()

    def test_inbound_responder_skipped_on_node(self):
        coord = MagicMock()
        tx = MagicMock()
        tx.meshtastic_enabled = True
        tx.source_node_id = 0xAABBCCDD
        _setup_inbound_responder(coord, tx, _node_config())
        coord.on_packet.assert_not_called()

    def test_telemetry_broadcaster_none_on_node(self):
        tx = MagicMock()
        tx.meshtastic_enabled = True
        coord = MagicMock()
        self.assertIsNone(
            _build_telemetry_broadcaster(_node_config(), tx, coord)
        )

    def test_position_broadcaster_none_on_node(self):
        tx = MagicMock()
        tx.meshtastic_enabled = True
        coord = MagicMock()
        self.assertIsNone(
            _build_position_broadcaster(_node_config(), tx, coord)
        )

    def test_bootstrap_pki_runs_on_gateway(self):
        coord = MagicMock()
        coord._crypto = MagicMock()
        coord._router.meshtastic_decoder = MagicMock()
        with patch("src.identity.keypair.KeypairStore") as mock_store:
            instance = mock_store.return_value
            instance.load_or_create.return_value = MagicMock(
                private_key=b"\x01" * 32,
                public_key=b"\x02" * 32,
            )
            _bootstrap_pki(_gateway_config(), coord)
            mock_store.assert_called_once()


if __name__ == "__main__":
    unittest.main()
