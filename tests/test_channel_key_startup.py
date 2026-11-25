"""Regression for #186: a malformed saved secondary PSK must fail closed."""

import asyncio
import base64
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

from fastapi.testclient import TestClient

from src.api import server
from src.config import TransmitConfig, load_config
from src.transmit.tx_service import TxService
from tests.auth_test_helpers import override_as_admin


class TestChannelKeyStartup(unittest.TestCase):
    def test_dashboard_survives_bad_slot_and_recovers_after_edit(self):
        private = bytes(range(16))
        valid = base64.b64encode(private).decode()
        invalid = valid.rstrip("=")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "local.yaml"
            path.write_text(f"meshtastic:\n  channel_keys:\n    Broken: '{invalid}'\n    Working: '{valid}'\n")
            original = path.read_bytes()
            with patch.dict(os.environ, CONCENTRATOR_CONFIG=str(path)):
                cfg = load_config(str(path))
                cfg.storage.database_path = str(Path(tmp) / "test.db")
                cfg.capture.sources = []
                cfg.capture.meshcore_usb.auto_detect = False
                cfg.upstream.enabled = False
                cfg.transmit.enabled = False
                cfg.meshcore.channel_keys = {"Broken": "11" * 16}
                cfg.dashboard.static_dir = str(Path(__file__).resolve().parents[1] / "frontend")
                app = server.create_app(cfg)
                override_as_admin(app)
                with patch.object(server, "validate_activation"), self.assertLogs(
                    "src.decode.crypto_service", level="WARNING"
                ) as logs, TestClient(app) as client:
                    self.assertEqual(client.get("/").status_code, 200)
                    self.assertEqual(path.read_bytes(), original)
                    crypto = server.pipeline._crypto
                    tx = TxService(crypto=crypto, transmit_config=TransmitConfig(enabled=True, node_id=1234),
                                   persist_derived_node_id=False)
                    tx._resolve_serial_send_source = AsyncMock()
                    tx._get_builder = Mock()
                    tx._meshtasticd_tx = Mock()
                    result = asyncio.run(tx.send_text("dummy", 123, channel=1))
                    self.assertFalse(result.success)
                    self.assertIn("Broken", result.error)
                    tx._resolve_serial_send_source.assert_not_awaited()
                    tx._get_builder.assert_not_called()
                    tx._meshtasticd_tx.send_text.assert_not_called()
                    self.assertIsNone(crypto.get_channel_key("Broken"))
                    self.assertEqual(crypto.get_all_keys()[1:3], [None, private])
                    self.assertEqual(tx._resolve_channel(2)[1], private)
                    self.assertNotEqual(tx._resolve_channel(0)[1], private)
                    valid_hash, _ = tx._resolve_channel(2)
                    self.assertEqual(tx._resolve_channel_by_hash(valid_hash)[1], private)
                    primary_hash, _ = tx._resolve_channel(0)
                    unknown_hash = next(h for h in range(1, 256) if h not in (valid_hash, primary_hash))
                    self.assertIsNone(tx._resolve_channel_by_hash(unknown_hash)[1])
                    original_packet = Mock(packet_id="00000001", source_id="00000002", channel_hash=unknown_hash)
                    self.assertFalse(asyncio.run(tx.send_routing_ack(original_packet)).success)
                    tx._get_builder.return_value.build_routing_ack.assert_not_called()
                    with self.assertRaises(ValueError):
                        tx._resolve_channel(1)

                    channels = [
                        {"index": 1, "name": "Broken", "psk_b64": invalid},
                        {"index": 2, "name": "Working", "psk_b64": valid},
                    ]
                    response = client.put("/api/config/channels", json={"channels": channels})
                    self.assertEqual(response.status_code, 400)
                    self.assertNotIn(invalid, response.text)
                    self.assertEqual(path.read_bytes(), original)
                    channels[0]["psk_b64"] = valid
                    response = client.put("/api/config/channels", json={"channels": channels})
                    self.assertEqual(response.status_code, 200, response.text)
                    self.assertEqual(tx._resolve_channel(1)[1], private)
                    self.assertEqual(tx._resolve_channel(2)[1], private)
                self.assertIn("Broken", " ".join(logs.output))
                self.assertNotIn(invalid, " ".join(logs.output))
