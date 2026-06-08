"""Unit tests for remote ADMIN config write (PR 16)."""
from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, MagicMock

from meshtastic.protobuf import admin_pb2

from src.admin.reader import AdminConfigError, AdminConfigReader
from src.admin.write_store import WriteOperationStore
from src.admin.writer import AdminConfigWriter, ROLE_CONFIRM_TOKEN
from src.transmit.tx_service import SendResult


class TestAdminWriterValidation(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.reader = MagicMock(spec=AdminConfigReader)
        self.reader.available = True
        self.reader.send_admin_to_node = AsyncMock(
            return_value=SendResult(success=True, packet_id="00000001")
        )
        self.writer = AdminConfigWriter(
            reader=self.reader,
            tx_service=MagicMock(meshtastic_enabled=True),
            write_store=WriteOperationStore(),
        )

    async def test_role_requires_confirm(self):
        with self.assertRaises(AdminConfigError) as ctx:
            await self.writer.apply_changes("a3f2b1c0", role=2)
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("CONFIRM", str(ctx.exception))

    async def test_rejects_empty_payload(self):
        with self.assertRaises(AdminConfigError) as ctx:
            await self.writer.apply_changes("a3f2b1c0")
        self.assertEqual(ctx.exception.status_code, 400)

    async def test_owner_write_sends_admin(self):
        result = await self.writer.apply_changes(
            "a3f2b1c0",
            long_name="Mesh Node",
            short_name="MN",
        )
        self.assertEqual(result["status"], "verifying")
        self.reader.send_admin_to_node.assert_awaited()
        call_args = self.reader.send_admin_to_node.await_args
        admin_msg = call_args.args[1]
        self.assertTrue(admin_msg.HasField("set_owner"))

    async def test_role_write_with_confirm(self):
        await self.writer.apply_changes(
            "a3f2b1c0",
            role=2,
            role_confirm=ROLE_CONFIRM_TOKEN,
        )
        admin_msg = self.reader.send_admin_to_node.await_args.args[1]
        self.assertEqual(admin_msg.set_config.device.role, 2)

    async def test_telemetry_module_write(self):
        await self.writer.apply_changes(
            "a3f2b1c0",
            telemetry_interval_secs=300,
        )
        admin_msg = self.reader.send_admin_to_node.await_args.args[1]
        self.assertEqual(
            admin_msg.set_module_config.telemetry.device_update_interval,
            300,
        )


class TestWriteStoreDebounce(unittest.TestCase):
    def test_blocks_rapid_writes(self):
        store = WriteOperationStore()
        store.begin("a3f2b1c0", changes={"role": 2}, verify_sections=["device"])
        store.mark_verifying("a3f2b1c0", ["00000001"])
        ok, _ = store.can_write("a3f2b1c0")
        self.assertFalse(ok)
