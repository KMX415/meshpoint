"""Edge-case tests for message API route helpers."""

from __future__ import annotations

import unittest
from types import SimpleNamespace

try:
    from fastapi import HTTPException
    from src.api.routes import messages
    _HAS_FASTAPI = True
except ModuleNotFoundError:  # pragma: no cover - environment dependent
    HTTPException = Exception
    messages = None
    _HAS_FASTAPI = False


class _StubMessageRepo:
    async def get_conversations(self, include_overheard=False):
        return []


class _StubNodeRepo:
    def __init__(self, nodes):
        self._nodes = nodes

    async def get_all(self):
        return self._nodes


@unittest.skipUnless(_HAS_FASTAPI, "fastapi is not installed in this environment")
class TestMessageRoutes(unittest.IsolatedAsyncioTestCase):
    """Keep route behavior stable for common UI edge cases."""

    async def test_send_message_rejects_whitespace_only_text(self):
        messages.init_routes(
            tx_service=SimpleNamespace(),
            message_repo=_StubMessageRepo(),
            node_repo=None,
            meshcore_tx=None,
            config=None,
        )
        with self.assertRaises(HTTPException) as ctx:
            await messages.send_message(messages.SendRequest(text="   "))
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("cannot be empty", str(ctx.exception.detail))

    async def test_send_message_requires_transmit_service(self):
        messages.init_routes(
            tx_service=None,
            message_repo=_StubMessageRepo(),
            node_repo=None,
            meshcore_tx=None,
            config=None,
        )
        with self.assertRaises(HTTPException) as ctx:
            await messages.send_message(messages.SendRequest(text="hello"))
        self.assertEqual(ctx.exception.status_code, 503)
        self.assertIn("Transmit service not available", str(ctx.exception.detail))

    async def test_get_contacts_filters_synthetic_node_ids(self):
        node_repo = _StubNodeRepo([
            {"node_id": "rf_log", "long_name": "RF Log"},
            {"node_id": "mc:channel", "long_name": "MeshCore Channel"},
            {"node_id": "mc:abc123", "long_name": "MeshCore Synthetic"},
            {"node_id": "abcd1234", "long_name": "Field Node"},
        ])
        messages.init_routes(
            tx_service=None,
            message_repo=_StubMessageRepo(),
            node_repo=node_repo,
            meshcore_tx=None,
            config=None,
        )

        contacts = await messages.get_contacts()
        self.assertEqual(len(contacts), 1)
        self.assertEqual(contacts[0]["node_id"], "abcd1234")
        self.assertEqual(contacts[0]["name"], "Field Node")

    async def test_get_channels_falls_back_to_preset_when_primary_blank(self):
        cfg = SimpleNamespace(
            meshtastic=SimpleNamespace(
                primary_channel_name="",
                channel_keys={},
            ),
            radio=SimpleNamespace(
                spreading_factor=11,
                bandwidth_khz=250.0,
            ),
        )
        messages.init_routes(
            tx_service=None,
            message_repo=_StubMessageRepo(),
            node_repo=None,
            meshcore_tx=None,
            config=cfg,
        )

        channels = await messages.get_channels()
        self.assertEqual(channels[0]["name"], "LongFast")


if __name__ == "__main__":
    unittest.main()
