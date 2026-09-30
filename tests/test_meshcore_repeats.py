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
