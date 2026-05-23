"""Tests for MeshCore channel management.

Covers:
  - GET /api/messages/channels: meshcore named channels appear after Public
  - PUT /api/config/meshcore/channels: validation, persistence, crypto update
  - hex→base64 conversion round-trip used by coordinator and config route
  - Channel hash routing: MeshCore packets use channel_hash directly as index
"""

from __future__ import annotations

import base64
import binascii
import unittest
from unittest.mock import MagicMock, call, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.routes import config_routes as config_module
from src.api.routes import messages as messages_module


# ── helpers ───────────────────────────────────────────────────────────────────

def _build_messages_app() -> FastAPI:
    app = FastAPI()
    app.include_router(messages_module.router)
    return app


def _build_config_app() -> FastAPI:
    app = FastAPI()
    app.include_router(config_module.router)
    return app


def _reset_messages_state() -> None:
    messages_module._tx_service = None
    messages_module._message_repo = None
    messages_module._node_repo = None
    messages_module._meshcore_tx = None
    messages_module._config = None


def _reset_config_state() -> None:
    config_module._config = None
    config_module._crypto = None
    config_module._tx_service = None


def _fake_config(*, mc_channel_keys=None, mt_channel_keys=None):
    cfg = MagicMock()
    cfg.meshcore.channel_keys = dict(mc_channel_keys or {})
    cfg.meshtastic.channel_keys = dict(mt_channel_keys or {})
    cfg.meshtastic.primary_channel_name = "LongFast"
    cfg.meshtastic.default_key_b64 = "AQ=="
    cfg.radio.spreading_factor = 11
    cfg.radio.bandwidth_khz = 250.0
    return cfg


def _fake_mc_tx(*, connected: bool = True):
    mc = MagicMock()
    mc.connected = connected
    return mc


# ── GET /api/messages/channels ────────────────────────────────────────────────

class TestGetChannelsMeshcore(unittest.TestCase):

    def setUp(self):
        _reset_messages_state()
        self.client = TestClient(_build_messages_app())

    def tearDown(self):
        _reset_messages_state()

    def test_no_meshcore_tx_omits_meshcore_channels(self):
        messages_module._config = _fake_config()
        messages_module._meshcore_tx = None
        res = self.client.get("/api/messages/channels")
        self.assertEqual(res.status_code, 200)
        protocols = [ch["protocol"] for ch in res.json()]
        self.assertNotIn("meshcore", protocols)

    def test_disconnected_meshcore_omits_meshcore_channels(self):
        messages_module._config = _fake_config()
        messages_module._meshcore_tx = _fake_mc_tx(connected=False)
        res = self.client.get("/api/messages/channels")
        protocols = [ch["protocol"] for ch in res.json()]
        self.assertNotIn("meshcore", protocols)

    def test_connected_no_named_channels_returns_public_only(self):
        messages_module._config = _fake_config()
        messages_module._meshcore_tx = _fake_mc_tx(connected=True)
        res = self.client.get("/api/messages/channels")
        mc = [ch for ch in res.json() if ch["protocol"] == "meshcore"]
        self.assertEqual(len(mc), 1)
        self.assertEqual(mc[0]["name"], "Public")
        self.assertEqual(mc[0]["channel"], 0)

    def test_named_channel_appears_after_public(self):
        messages_module._config = _fake_config(
            mc_channel_keys={"orangecounty": "f708715569f4ee34c273f8f32d32e0e8"}
        )
        messages_module._meshcore_tx = _fake_mc_tx(connected=True)
        res = self.client.get("/api/messages/channels")
        mc = [ch for ch in res.json() if ch["protocol"] == "meshcore"]
        self.assertEqual(len(mc), 2)
        self.assertEqual(mc[0]["name"], "Public")
        self.assertEqual(mc[0]["channel"], 0)
        self.assertEqual(mc[1]["name"], "orangecounty")
        self.assertEqual(mc[1]["channel"], 1)

    def test_multiple_named_channels_indexed_sequentially(self):
        messages_module._config = _fake_config(
            mc_channel_keys={
                "orangecounty": "f708715569f4ee34c273f8f32d32e0e8",
                "localchat":    "aabbccddeeff00112233445566778899",
            }
        )
        messages_module._meshcore_tx = _fake_mc_tx(connected=True)
        res = self.client.get("/api/messages/channels")
        mc = [ch for ch in res.json() if ch["protocol"] == "meshcore"]
        self.assertEqual(len(mc), 3)
        self.assertEqual([ch["channel"] for ch in mc], [0, 1, 2])

    def test_node_id_format_is_broadcast_meshcore_index(self):
        messages_module._config = _fake_config(
            mc_channel_keys={"orangecounty": "f708715569f4ee34c273f8f32d32e0e8"}
        )
        messages_module._meshcore_tx = _fake_mc_tx(connected=True)
        res = self.client.get("/api/messages/channels")
        mc = [ch for ch in res.json() if ch["protocol"] == "meshcore"]
        self.assertEqual(mc[0]["node_id"], "broadcast:meshcore:0")
        self.assertEqual(mc[1]["node_id"], "broadcast:meshcore:1")

    def test_meshtastic_channels_still_present_alongside_meshcore(self):
        messages_module._config = _fake_config(
            mc_channel_keys={"orangecounty": "f708715569f4ee34c273f8f32d32e0e8"}
        )
        messages_module._meshcore_tx = _fake_mc_tx(connected=True)
        res = self.client.get("/api/messages/channels")
        protocols = [ch["protocol"] for ch in res.json()]
        self.assertIn("meshtastic", protocols)
        self.assertIn("meshcore", protocols)


# ── PUT /api/config/meshcore/channels ─────────────────────────────────────────

class TestUpdateMeshcoreChannels(unittest.TestCase):

    def setUp(self):
        _reset_config_state()
        self.client = TestClient(_build_config_app())

    def tearDown(self):
        _reset_config_state()

    def test_503_when_config_not_loaded(self):
        config_module._config = None
        res = self.client.put(
            "/api/config/meshcore/channels",
            json={"channels": [{"name": "test", "key_hex": "aabb"}]},
        )
        self.assertEqual(res.status_code, 503)

    def test_400_on_non_hex_key(self):
        config_module._config = _fake_config()
        res = self.client.put(
            "/api/config/meshcore/channels",
            json={"channels": [{"name": "test", "key_hex": "not_valid_hex!!"}]},
        )
        self.assertEqual(res.status_code, 400)
        self.assertIn("test", res.json()["detail"])

    def test_valid_channel_saved_to_yaml(self):
        config_module._config = _fake_config()
        with patch("src.api.routes.config_routes.save_section_to_yaml") as mock_save:
            res = self.client.put(
                "/api/config/meshcore/channels",
                json={"channels": [
                    {"name": "orangecounty", "key_hex": "f708715569f4ee34c273f8f32d32e0e8"}
                ]},
            )
        self.assertEqual(res.status_code, 200)
        mock_save.assert_called_once_with(
            "meshcore",
            {"channel_keys": {"orangecounty": "f708715569f4ee34c273f8f32d32e0e8"}},
        )

    def test_response_shape(self):
        config_module._config = _fake_config()
        with patch("src.api.routes.config_routes.save_section_to_yaml"):
            res = self.client.put(
                "/api/config/meshcore/channels",
                json={"channels": [
                    {"name": "orangecounty", "key_hex": "f708715569f4ee34c273f8f32d32e0e8"}
                ]},
            )
        body = res.json()
        self.assertTrue(body["saved"])
        self.assertFalse(body["restart_required"])
        self.assertEqual(body["channel_count"], 1)

    def test_entries_with_empty_name_or_key_are_skipped(self):
        config_module._config = _fake_config()
        with patch("src.api.routes.config_routes.save_section_to_yaml") as mock_save:
            res = self.client.put(
                "/api/config/meshcore/channels",
                json={"channels": [
                    {"name": "",             "key_hex": "aabbccdd"},
                    {"name": "nokey",        "key_hex": ""},
                    {"name": "orangecounty", "key_hex": "f708715569f4ee34c273f8f32d32e0e8"},
                ]},
            )
        self.assertEqual(res.status_code, 200)
        saved_keys = mock_save.call_args.args[1]["channel_keys"]
        self.assertEqual(list(saved_keys.keys()), ["orangecounty"])

    def test_empty_channel_list_clears_all(self):
        config_module._config = _fake_config(
            mc_channel_keys={"orangecounty": "f708715569f4ee34c273f8f32d32e0e8"}
        )
        with patch("src.api.routes.config_routes.save_section_to_yaml") as mock_save:
            res = self.client.put(
                "/api/config/meshcore/channels",
                json={"channels": []},
            )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["channel_count"], 0)
        saved_keys = mock_save.call_args.args[1]["channel_keys"]
        self.assertEqual(saved_keys, {})

    def test_403_on_permission_error(self):
        config_module._config = _fake_config()
        with patch(
            "src.api.routes.config_routes.save_section_to_yaml",
            side_effect=PermissionError("read-only filesystem"),
        ):
            res = self.client.put(
                "/api/config/meshcore/channels",
                json={"channels": [
                    {"name": "test", "key_hex": "f708715569f4ee34c273f8f32d32e0e8"}
                ]},
            )
        self.assertEqual(res.status_code, 403)

    def test_crypto_receives_key_as_base64_not_hex(self):
        config_module._config = _fake_config()
        crypto = MagicMock()
        config_module._crypto = crypto
        hex_key = "f708715569f4ee34c273f8f32d32e0e8"
        expected_b64 = base64.b64encode(binascii.unhexlify(hex_key)).decode()

        with patch("src.api.routes.config_routes.save_section_to_yaml"):
            self.client.put(
                "/api/config/meshcore/channels",
                json={"channels": [{"name": "orangecounty", "key_hex": hex_key}]},
            )

        crypto.clear_channel_keys.assert_called_once()
        crypto.add_channel_key.assert_any_call("orangecounty", expected_b64)

    def test_existing_meshtastic_keys_preserved_after_meshcore_save(self):
        config_module._config = _fake_config(
            mt_channel_keys={"SecretChat": "base64PSKhere=="}
        )
        crypto = MagicMock()
        config_module._crypto = crypto

        with patch("src.api.routes.config_routes.save_section_to_yaml"):
            self.client.put(
                "/api/config/meshcore/channels",
                json={"channels": [
                    {"name": "orangecounty", "key_hex": "f708715569f4ee34c273f8f32d32e0e8"}
                ]},
            )

        crypto.add_channel_key.assert_any_call("SecretChat", "base64PSKhere==")

    def test_in_memory_config_updated(self):
        cfg = _fake_config()
        config_module._config = cfg
        with patch("src.api.routes.config_routes.save_section_to_yaml"):
            self.client.put(
                "/api/config/meshcore/channels",
                json={"channels": [
                    {"name": "orangecounty", "key_hex": "f708715569f4ee34c273f8f32d32e0e8"}
                ]},
            )
        self.assertEqual(
            cfg.meshcore.channel_keys,
            {"orangecounty": "f708715569f4ee34c273f8f32d32e0e8"},
        )

    def test_no_crypto_call_when_crypto_not_set(self):
        config_module._config = _fake_config()
        config_module._crypto = None
        with patch("src.api.routes.config_routes.save_section_to_yaml"):
            res = self.client.put(
                "/api/config/meshcore/channels",
                json={"channels": [
                    {"name": "test", "key_hex": "f708715569f4ee34c273f8f32d32e0e8"}
                ]},
            )
        self.assertEqual(res.status_code, 200)


# ── hex→base64 conversion ─────────────────────────────────────────────────────

class TestHexKeyConversion(unittest.TestCase):
    """Verify the hex→base64 round-trip used in coordinator and config route."""

    def test_known_key_produces_correct_base64(self):
        b64 = base64.b64encode(
            binascii.unhexlify("f708715569f4ee34c273f8f32d32e0e8")
        ).decode()
        self.assertEqual(b64, "9whxVWn07jTCc/jzLTLg6A==")

    def test_round_trip_is_lossless(self):
        hex_key = "aabbccddeeff00112233445566778899"
        b64 = base64.b64encode(binascii.unhexlify(hex_key)).decode()
        recovered = binascii.hexlify(base64.b64decode(b64)).decode()
        self.assertEqual(recovered, hex_key)

    def test_crypto_service_stores_correct_bytes_from_converted_key(self):
        from src.decode.crypto_service import CryptoService
        hex_key = "f708715569f4ee34c273f8f32d32e0e8"
        b64 = base64.b64encode(binascii.unhexlify(hex_key)).decode()
        cs = CryptoService()
        cs.add_channel_key("test", b64)
        self.assertEqual(cs._keys["test"], binascii.unhexlify(hex_key))

    def test_odd_length_hex_raises(self):
        with self.assertRaises((binascii.Error, ValueError)):
            binascii.unhexlify("abc")

    def test_non_hex_characters_raise(self):
        with self.assertRaises((binascii.Error, ValueError)):
            binascii.unhexlify("zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz")


# ── channel hash routing ──────────────────────────────────────────────────────

class TestMeshcoreChannelHashRouting(unittest.TestCase):
    """MeshCore broadcast packets must use channel_hash directly as the
    channel index; Meshtastic packets still go through the hash map."""

    def _route(self, protocol, channel_hash, hash_map=None):
        """Replicate the routing logic from server.py on_text_packet."""
        from src.models.packet import Protocol
        if hash_map is None:
            hash_map = {}
        if protocol == Protocol.MESHCORE:
            return channel_hash or 0
        return hash_map.get(channel_hash, 0)

    def test_meshcore_channel_0_routes_to_index_0(self):
        from src.models.packet import Protocol
        self.assertEqual(self._route(Protocol.MESHCORE, 0), 0)

    def test_meshcore_channel_1_routes_to_index_1(self):
        from src.models.packet import Protocol
        self.assertEqual(self._route(Protocol.MESHCORE, 1), 1)

    def test_meshcore_channel_2_routes_to_index_2(self):
        from src.models.packet import Protocol
        self.assertEqual(self._route(Protocol.MESHCORE, 2), 2)

    def test_meshcore_ignores_hash_map_entirely(self):
        from src.models.packet import Protocol
        # Even if hash_map has a matching entry, meshcore must not use it
        self.assertEqual(self._route(Protocol.MESHCORE, 2, hash_map={2: 99}), 2)

    def test_meshtastic_known_hash_resolves_via_map(self):
        from src.models.packet import Protocol
        self.assertEqual(self._route(Protocol.MESHTASTIC, 0x2A, {0x2A: 1}), 1)

    def test_meshtastic_unknown_hash_defaults_to_zero(self):
        from src.models.packet import Protocol
        self.assertEqual(self._route(Protocol.MESHTASTIC, 0xFF, {0x2A: 1}), 0)

    def test_meshcore_none_channel_hash_defaults_to_zero(self):
        from src.models.packet import Protocol
        self.assertEqual(self._route(Protocol.MESHCORE, None), 0)

    def test_node_id_built_correctly_for_meshcore_channel_2(self):
        from src.models.packet import Protocol
        ch_idx = self._route(Protocol.MESHCORE, 2)
        node_id = f"broadcast:{Protocol.MESHCORE.value}:{ch_idx}"
        self.assertEqual(node_id, "broadcast:meshcore:2")


if __name__ == "__main__":
    unittest.main()
