"""Unit tests for remote ADMIN config read (PR 15)."""
from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from meshtastic.protobuf import admin_pb2, config_pb2, mesh_pb2

from src.admin.config_decode import _redact_value, message_to_redacted_dict
from src.admin.pending_store import PendingConfigStore
from src.admin.reader import AdminConfigError, AdminConfigReader, PORTNUM_ADMIN
from src.decode.crypto_service import CryptoService
from src.models.packet import Packet, PacketType, Protocol
from src.transmit.meshtastic_builder import MeshtasticPacketBuilder


class TestAdminMessageBuild(unittest.TestCase):
    def test_device_config_request_serializes(self):
        msg = admin_pb2.AdminMessage()
        msg.get_config_request = admin_pb2.AdminMessage.DEVICE_CONFIG
        self.assertEqual(msg.SerializeToString(), b"\x28\x00")

    def test_owner_request_serializes(self):
        msg = admin_pb2.AdminMessage()
        msg.get_owner_request = True
        self.assertEqual(msg.SerializeToString(), b"\x18\x01")


class TestConfigRedaction(unittest.TestCase):
    def test_psk_fields_redacted(self):
        raw = {
            "security": {"private_key": "secret", "public_key": "pub"},
            "lora": {"bandwidth": 250, "psk": "hide-me"},
        }
        out = _redact_value(raw)
        self.assertEqual(out["security"]["private_key"], "***")
        self.assertEqual(out["security"]["public_key"], "***")
        self.assertEqual(out["lora"]["psk"], "***")
        self.assertEqual(out["lora"]["bandwidth"], 250)

    def test_message_to_dict_keeps_safe_fields(self):
        cfg = config_pb2.Config()
        cfg.lora.bandwidth = 250
        out = message_to_redacted_dict(cfg)
        self.assertEqual(out["lora"]["bandwidth"], 250)


class TestPendingStore(unittest.TestCase):
    def test_debounce_blocks_second_request(self):
        store = PendingConfigStore()
        store.begin("a3f2b1c0", section="device", packet_id="00000001", expected_response="get_config_response")
        ok, _ = store.can_request("a3f2b1c0")
        self.assertFalse(ok)


class TestAdminPacketBuild(unittest.TestCase):
    def test_build_admin_packet_encrypts(self):
        crypto = CryptoService(default_key_b64="AQ==")
        admin_key = crypto._expand_key(b"\x01")
        builder = MeshtasticPacketBuilder(crypto)
        admin_msg = admin_pb2.AdminMessage()
        admin_msg.get_config_request = admin_pb2.AdminMessage.DEVICE_CONFIG
        packet = builder.build_admin_message(
            admin_payload=admin_msg.SerializeToString(),
            dest=0xA3F2B1C0,
            source_id=0x12345678,
            packet_id=99,
            admin_key=admin_key,
            admin_channel_name="admin",
        )
        self.assertIsNotNone(packet)
        self.assertGreater(len(packet), 16)


class TestAdminResponseConsume(unittest.IsolatedAsyncioTestCase):
    async def test_consumes_matching_admin_response(self):
        crypto = CryptoService(default_key_b64="AQ==")
        admin_key = crypto._expand_key(b"\x01")
        builder = MeshtasticPacketBuilder(crypto)

        response_admin = admin_pb2.AdminMessage()
        response_admin.get_config_response.device.role = 2
        inner = builder._serialize_data(
            PORTNUM_ADMIN, response_admin.SerializeToString()
        )

        packet_id = 42
        source_id = 0xA3F2B1C0
        ciphertext = crypto.encrypt_meshtastic(inner, packet_id, source_id, key=admin_key)
        header = builder._build_header(
            0x12345678,
            source_id,
            packet_id,
            channel_hash=crypto.compute_channel_hash("admin", admin_key),
        )
        raw = header + ciphertext

        tx = MagicMock()
        tx.meshtastic_enabled = True
        tx.send_admin_message = AsyncMock(
            return_value=MagicMock(success=True, packet_id="0000002a", error="")
        )

        reader = AdminConfigReader(
            tx_service=tx,
            crypto=crypto,
            admin_key_b64="AQ==",
            admin_channel_name="admin",
            local_node_id=0x12345678,
        )
        await reader.request_config("!a3f2b1c0", section="device")

        packet = Packet(
            packet_id="0000002a",
            source_id="a3f2b1c0",
            destination_id="12345678",
            protocol=Protocol.MESHTASTIC,
            packet_type=PacketType.ADMIN,
            raw_radio_packet=raw,
        )
        reader.try_consume_packet(packet)

        status = reader.get_status("a3f2b1c0")
        self.assertEqual(status["status"], "complete")
        self.assertIn("config", status["config"])


class TestAdminReaderUnavailable(unittest.IsolatedAsyncioTestCase):
    async def test_503_without_admin_key(self):
        reader = AdminConfigReader(tx_service=MagicMock(), crypto=CryptoService())
        with self.assertRaises(AdminConfigError) as ctx:
            await reader.request_config("a3f2b1c0")
        self.assertEqual(ctx.exception.status_code, 503)
