"""Protocol fixtures exercise authenticated echoes and independent DM ACKs."""
import hashlib
import hmac
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from Crypto.Cipher import AES
from meshcore import EventType

from src.storage.database import DatabaseManager
from src.storage.message_repository import MessageRepository
from src.transmit.meshcore_repeats import MeshcoreHeardRepeats
from src.transmit.meshcore_tx_client import MeshCoreTxClient

SECRET = bytes(range(16))
CHANNEL = {"channel_secret": SECRET, "channel_name": "test"}


def frame(text="Bench: hello", timestamp=100, hops=1, width=1, scoped=False, secret=SECRET):
    plain = timestamp.to_bytes(4, "little") + b"\0" + text.encode()
    encrypted = AES.new(secret, AES.MODE_ECB).encrypt(plain + bytes((-len(plain)) % 16))
    body = hashlib.sha256(secret).digest()[:1] + hmac.digest(secret, encrypted, "sha256")[:2] + encrypted
    header = bytes([20 if scoped else 21]) + (bytes(4) if scoped else b"")
    return {"payload": (header + bytes([(width - 1) * 64 + hops]) + b"\xaa" * (hops * width) + body).hex()}


class FeedbackTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.db = DatabaseManager(":memory:")
        await self.db.connect()
        self.repo = MessageRepository(self.db)
        self.broadcast = AsyncMock()
        self.tracker = MeshcoreHeardRepeats(self.repo, self.broadcast)

    async def asyncTearDown(self):
        await self.db.disconnect()

    async def bind(self, item, node="broadcast:meshcore"):
        row = await self.repo.save_sent("hello", node, "Bench", "meshcore", packet_id=item.packet_id)
        return row, await self.tracker.bind(item.packet_id, row, node)

    async def test_early_echoes_persist_and_later_observations_are_live(self):
        item = self.tracker.begin(CHANNEL, "Bench", "hello", 100)
        await self.tracker.observe(frame())
        await self.tracker.observe(frame(hops=2, width=3, scoped=True))
        self.broadcast.assert_not_called()
        row, feedback = await self.bind(item)
        self.assertEqual(feedback["heard_repeats"], 2)
        await self.tracker.observe(frame())
        message = (await self.repo.get_conversation("broadcast:meshcore"))[0]
        self.assertEqual(message.heard_repeats, 3)
        self.assertEqual(message.status, "sent")
        self.assertEqual(message.rx_count, 1)
        self.assertEqual(self.broadcast.call_args.args[1]["id"], row)

    async def test_unrelated_invalid_and_unrepeated_packets_do_not_count(self):
        item = self.tracker.begin(CHANNEL, "Bench", "hello", 100)
        for payload in [frame(hops=0), frame(timestamp=101), frame(text="Other: hello"),
                        frame(secret=b"x" * 16), {"payload": "zz"}, {"payload": "15"},
                        {"payload": frame()["payload"][:-2]}, {"payload": "00" * 600}]:
            await self.tracker.observe(payload)
        bad_mac = bytearray.fromhex(frame()["payload"])
        bad_mac[4] ^= 1
        await self.tracker.observe({"payload": bad_mac.hex()})
        self.assertEqual(item.count, 0)

    async def test_same_text_different_send_and_channel(self):
        first = self.tracker.begin(CHANNEL, "Bench", "hello", 100)
        second = self.tracker.begin(CHANNEL, "Bench", "hello", 101)
        await self.tracker.observe(frame(timestamp=101))
        self.assertEqual((first.count, second.count), (0, 1))
        self.assertNotEqual(first.packet_id, second.packet_id)

    async def test_dm_ack_before_send_response_and_storage(self):
        item = self.tracker.begin_direct()
        await self.tracker.acknowledge({"code": "12345678"})
        self.tracker.expect_ack(item, {"expected_ack": bytes.fromhex("12345678")})
        _, feedback = await self.bind(item, "mc:recipient")
        self.assertEqual(feedback, {"heard_repeats": None, "status": "delivered"})
        message = (await self.repo.get_conversation("mc:recipient"))[0]
        self.assertEqual(message.status, "delivered")
        self.assertIsNone(message.heard_repeats)

    async def test_dm_ack_after_storage_matches_only_its_token(self):
        item = self.tracker.begin_direct()
        self.tracker.expect_ack(item, {"expected_ack": bytes.fromhex("12345678")})
        await self.bind(item, "mc:recipient")
        await self.tracker.acknowledge({"code": "87654321"})
        await self.tracker.observe(frame())
        self.assertEqual(item.status, "sent")
        self.assertIsNone(item.count)
        await self.tracker.acknowledge({"code": "12345678"})
        self.assertEqual((await self.repo.get_conversation("mc:recipient"))[0].status, "delivered")

    async def test_old_ack_and_expired_pending_do_not_confirm_new_send(self):
        await self.tracker.acknowledge({"code": "12345678"})
        item = self.tracker.begin_direct()
        self.tracker.expect_ack(item, {"expected_ack": bytes.fromhex("12345678")})
        self.assertEqual(item.status, "sent")
        item.created -= 901
        await self.tracker.acknowledge({"code": "12345678"})
        self.assertNotIn(item.packet_id, self.tracker.pending)
        for _ in range(140):
            self.tracker.begin_direct()
        self.assertEqual(len(self.tracker.pending), 128)

    async def test_deleted_rows_not_recreated_and_counts_never_regress(self):
        item = self.tracker.begin(CHANNEL, "Bench", "hello", 100)
        row, _ = await self.bind(item)
        await self.repo.update_meshcore_feedback(row, 9, "sent")
        await self.repo.update_meshcore_feedback(row, 2, "sent")
        self.assertEqual((await self.repo.get_conversation("broadcast:meshcore"))[0].heard_repeats, 9)
        await self.repo.delete_conversation("broadcast:meshcore")
        self.broadcast.reset_mock()
        await self.tracker.observe(frame())
        self.broadcast.assert_not_called()

    async def test_dm_client_preserves_early_ack_and_discards_rejection(self):
        client = MeshCoreTxClient()
        client.repeat_tracker = self.tracker
        mc = SimpleNamespace(commands=SimpleNamespace(send_msg=AsyncMock()))
        client.set_connection(mc)

        async def send(*args, **kwargs):
            await self.tracker.acknowledge({"code": "12345678"})
            return SimpleNamespace(type=EventType.MSG_SENT, payload={"expected_ack": bytes.fromhex("12345678")})

        mc.commands.send_msg.side_effect = send
        result = await client.send_direct_message("aabbccddeeff", "hello")
        self.assertTrue(result.success)
        self.assertEqual(result.status, "delivered")
        self.assertIsNone(result.heard_repeats)
        mc.commands.send_msg.side_effect = None
        mc.commands.send_msg.return_value = SimpleNamespace(type=EventType.ERROR, payload={"reason": "rejected"})
        rejected = await client.send_direct_message("aabbccddeeff", "hello")
        self.assertFalse(rejected.success)
        self.assertNotIn(rejected.packet_id, self.tracker.pending)

    async def test_path_signal_bound_and_name_ambiguity(self):
        item = self.tracker.begin(CHANNEL, "Bench", "hello", 100)
        raw = frame(width=2)
        raw.update(rssi=-96, snr=7.25)
        await self.tracker.observe(raw)
        row, _ = await self.bind(item)
        for key, name in [("aaaa" + "11" * 30, "Hilltop"), ("aaaa" + "22" * 30, "Valley")]:
            await self.db.execute(
                "INSERT INTO nodes (node_id, protocol, long_name, last_heard, first_seen) VALUES (?, 'meshcore', ?, '', '')",
                (key, name),
            )
        data = await self.repo.get_heard_paths(row)
        self.assertTrue(data["recorded"])
        observed = data["observations"][0]
        self.assertEqual(observed["path"], ["aaaa"])
        self.assertEqual((observed["rssi"], observed["snr"]), (-96, 7.25))
        self.assertTrue(observed["hops"][0]["ambiguous"])
        self.assertIsNone(observed["hops"][0]["name"])
        for _ in range(35):
            await self.tracker.observe(frame())
        data = await self.repo.get_heard_paths(row)
        self.assertEqual(data["count"], 36)
        self.assertEqual(len(data["observations"]), 32)
        await self.repo.update_meshcore_feedback(row, 1, "sent", [])
        self.assertEqual(len((await self.repo.get_heard_paths(row))["observations"]), 32)
        self.assertIsNone(await self.repo.get_heard_paths(99999))

    async def test_missing_signal_old_message_and_unique_name(self):
        old = await self.repo.save_sent("old", "broadcast:meshcore", "", "meshcore", heard_repeats=2)
        self.assertFalse((await self.repo.get_heard_paths(old))["recorded"])
        item = self.tracker.begin(CHANNEL, "Bench", "hello", 100)
        row, _ = await self.bind(item)
        await self.db.execute(
            "INSERT INTO nodes (node_id, protocol, long_name, last_heard, first_seen) VALUES (?, 'meshcore', ?, '', '')",
            ("aa" + "11" * 31, "Hilltop"),
        )
        await self.tracker.observe({**frame(), "rssi": float("nan"), "snr": True})
        observed = (await self.repo.get_heard_paths(row))["observations"][0]
        self.assertIsNone(observed["rssi"])
        self.assertIsNone(observed["snr"])
        self.assertEqual(observed["hops"][0]["name"], "Hilltop")

    async def test_existing_database_migration_preserves_counts_and_is_idempotent(self):
        row = await self.repo.save_sent("old", "broadcast:meshcore", "", "meshcore", heard_repeats=3)
        await self.db.execute("ALTER TABLE messages DROP COLUMN heard_paths")
        await self.db._run_migrations()
        await self.db._run_migrations()
        details = await self.repo.get_heard_paths(row)
        self.assertEqual(details["count"], 3)
        self.assertFalse(details["recorded"])

    async def test_observations_survive_tracker_recreation(self):
        item = self.tracker.begin(CHANNEL, "Bench", "hello", 100)
        row, _ = await self.bind(item)
        await self.tracker.observe({**frame(), "rssi": -104, "snr": -3})
        self.tracker = MeshcoreHeardRepeats(self.repo, self.broadcast)
        details = await MessageRepository(self.db).get_heard_paths(row)
        self.assertEqual(details["observations"][0]["rssi"], -104)
        self.assertEqual(details["count"], 1)

    async def test_detail_endpoint_returns_saved_evidence_and_not_found(self):
        from unittest.mock import patch
        from fastapi import HTTPException
        from src.api.routes import messages
        row = await self.repo.save_sent("old", "broadcast:meshcore", "", "meshcore")
        with patch.object(messages, "_message_repo", self.repo):
            self.assertFalse((await messages.get_heard_paths(row))["recorded"])
            with self.assertRaises(HTTPException) as error:
                await messages.get_heard_paths(99999)
            self.assertEqual(error.exception.status_code, 404)
