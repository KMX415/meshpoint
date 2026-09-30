"""Correlate companion RX logs with our channel sends; no forwarding logic.

The installed MeshCore SDK authenticates/decrypts channel packets. Matching uses
the channel secret, exact on-air text and timestamp, never a short hash alone.
Only copies with a repeater path count. Counts are local observations, not ACKs.
"""

import asyncio
import hashlib
import time
import uuid
from dataclasses import dataclass, field


@dataclass
class PendingRepeat:
    packet_id: str
    timestamp: int
    message: str
    parser: object
    created: float = field(default_factory=time.monotonic)
    count: int | None = 0
    row_id: int | None = None
    node_id: str = ""
    expected_ack: str = ""
    status: str = "sent"
    ack_floor: int = 0


class MeshcoreHeardRepeats:
    def __init__(self, repository, broadcast):
        self.repository = repository
        self.broadcast = broadcast
        self.pending = {}
        self._acks = {}
        self._ack_sequence = 0
        self._lock = asyncio.Lock()

    def _prune(self):
        now = time.monotonic()
        for key, item in list(self.pending.items()):
            if now - item.created > 900:
                del self.pending[key]
        for key, (_, arrived) in list(self._acks.items()):
            if now - arrived > 30:
                del self._acks[key]
        while len(self.pending) > 128:
            del self.pending[next(iter(self.pending))]

    def begin(self, channel, sender, text, timestamp):
        from meshcore.meshcore_parser import MeshcorePacketParser

        secret = channel.get("channel_secret")
        if not isinstance(secret, bytes) or len(secret) != 16 or not sender:
            return None
        self._prune()
        parser = MeshcorePacketParser()
        parser.channels = [{**channel, "channel_hash": hashlib.sha256(secret).hexdigest()[:2]}]
        parser.decrypt_channels = True
        item = PendingRepeat("mc:" + uuid.uuid4().hex, timestamp, f"{sender}: {text}", parser)
        self.pending[item.packet_id] = item
        self._prune()
        return item

    def begin_direct(self):
        # Stock companions expose an ACK token, not the encrypted TX packet.
        # None means repeat tracking unavailable, rather than zero observations.
        item = PendingRepeat("mc:" + uuid.uuid4().hex, 0, "", None, count=None)
        item.ack_floor = self._ack_sequence
        self.pending[item.packet_id] = item
        self._prune()
        return item

    def expect_ack(self, item, payload):
        token = payload.get("expected_ack")
        if not isinstance(token, bytes) or len(token) != 4:
            return
        item.expected_ack = token.hex()
        if self._acks.get(item.expected_ack, (0, 0))[0] > item.ack_floor:
            item.status = "delivered"

    async def acknowledge(self, payload):
        code = payload.get("code")
        if not isinstance(code, str) or len(code) != 8:
            return
        try:
            bytes.fromhex(code)
        except ValueError:
            return
        code = code.lower()
        async with self._lock:
            self._prune()
            self._ack_sequence += 1
            self._acks[code] = (self._ack_sequence, time.monotonic())
            while len(self._acks) > 128:
                del self._acks[next(iter(self._acks))]
            for item in self.pending.values():
                if item.expected_ack == code and item.status != "delivered":
                    item.status = "delivered"
                    if item.row_id is not None:
                        await self._publish(item)

    def discard(self, packet_id):
        self.pending.pop(packet_id, None)

    async def bind(self, packet_id, row_id, node_id):
        async with self._lock:
            item = self.pending.get(packet_id)
            if item is None:
                return None
            item.row_id, item.node_id = row_id, node_id
            await self._publish(item)
            return {"heard_repeats": item.count, "status": item.status}

    async def observe(self, payload):
        raw = payload.get("payload")
        if not isinstance(raw, str) or len(raw) > 1024:
            return
        try:
            frame = bytes.fromhex(raw)
        except ValueError:
            return
        if len(frame) < 2 or (frame[0] >> 2) & 15 != 5 or frame[0] >> 6 != 0:
            return
        # Channel messages use flood routes; transport-scoped floods add 4 bytes.
        route = frame[0] & 3
        if route not in (0, 1):
            return
        offset = 5 if route == 0 else 1
        if len(frame) <= offset:
            return
        path = frame[offset]
        hops, width = path & 63, (path >> 6) + 1
        body_start = offset + 1 + hops * width
        if not hops or width > 3 or len(frame) < body_start + 19 or (len(frame) - body_start - 3) % 16:
            return
        async with self._lock:
            self._prune()
            for item in self.pending.values():
                if item.parser is None:
                    continue
                # SDK caching uses a short hash; bypass it for exact correlation.
                item.parser.channels_log.clear()
                try:
                    decoded = await item.parser.parsePacketPayload(frame, {})
                except (ValueError, IndexError, KeyError):
                    continue
                if decoded.get("sender_timestamp") != item.timestamp or decoded.get("message") != item.message:
                    continue
                item.count += 1
                if item.row_id is not None:
                    await self._publish(item)
                return

    async def _publish(self, item):
        saved = await self.repository.update_meshcore_feedback(item.row_id, item.count, item.status)
        if saved:
            await self.broadcast("message_repeats", {
                "id": item.row_id, "packet_id": item.packet_id,
                "node_id": item.node_id, "protocol": "meshcore",
                "heard_repeats": item.count,
                "status": item.status,
            })
