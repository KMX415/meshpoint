"""MQTT egress policy: broadcasts only, and privacy across every packet format."""
from copy import deepcopy
from dataclasses import replace
import json
import socket
import struct
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from meshtastic.protobuf.mesh_pb2 import Data, Position
from meshtastic.protobuf.mqtt_pb2 import ServiceEnvelope

from src.config import MqttConfig
from src.models.packet import Packet, PacketType, Protocol
from src.relay import mqtt_publisher as module
from src.relay.mqtt_privacy import prepare_packet
from src.relay.mqtt_publisher import HomeAssistantDiscovery, MqttPublisher


@pytest.fixture(autouse=True)
def forbid_connections(monkeypatch):
    def blocked(*args, **kwargs):
        raise AssertionError("MQTT privacy tests must not connect to a network")
    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setattr(socket.socket, "connect_ex", blocked)
    monkeypatch.setattr(socket, "create_connection", blocked)
    if module.paho_mqtt is None:
        monkeypatch.setattr(module, "paho_mqtt", SimpleNamespace(MQTT_ERR_SUCCESS=0))


def packet(**changes):
    return replace(Packet(packet_id="12345678", source_id="11223344",
                          destination_id="ffffffff", protocol=Protocol.MESHTASTIC,
                          packet_type=PacketType.TEXT, decrypted=True,
                          decoded_payload={"text": "synthetic broadcast"}), **changes)


def publisher(**settings):
    config = MqttConfig(enabled=True, broker="invalid.invalid", publish_json=True,
                        homeassistant_discovery=True)
    for key, value in settings.items():
        setattr(config, key, value)
    pub = MqttPublisher(config, "offline-fixture")
    client = Mock()
    client.publish.return_value = SimpleNamespace(rc=0)
    pub._client, pub._connected = client, True
    pub._ha_discovery = HomeAssistantDiscovery(client, pub.gateway_id)
    return pub, client, config


@pytest.mark.parametrize("protocol,destination", [
    (Protocol.MESHTASTIC, "55667788"), (Protocol.MESHTASTIC, "ffff"),
    (Protocol.MESHTASTIC, "broadcast"), (Protocol.MESHTASTIC, None),
    (Protocol.MESHTASTIC, ""), (Protocol.MESHTASTIC, "unknown"),
    (Protocol.MESHTASTIC, " ffffffff"), (Protocol.MESHTASTIC, 0xffffffff),
    (Protocol.MESHCORE, "self"), (Protocol.MESHCORE, "unknown"),
    (Protocol.MESHCORE, "1234"), (Protocol.MESHCORE, "ffffffff"),
    (Protocol.UNKNOWN, "ffffffff"),
])
def test_only_explicit_protocol_broadcasts_can_reach_any_sink(protocol, destination):
    pub, client, _ = publisher(publish_channels=["LongFast", "MeshCore", "private"])
    assert not pub.publish(packet(protocol=protocol, destination_id=destination))
    client.publish.assert_not_called()


@pytest.mark.parametrize("protocol,destination", [
    (Protocol.MESHTASTIC, "ffffffff"), (Protocol.MESHTASTIC, "FFFFFFFF"),
    (Protocol.MESHCORE, "ffff"), (Protocol.MESHCORE, "broadcast"),
])
def test_allowlisted_broadcasts_keep_working(protocol, destination):
    pub, client, _ = publisher()
    assert pub.publish(packet(protocol=protocol, destination_id=destination))
    assert client.publish.called


def test_channel_and_enabled_gates_remain_required():
    pub, client, config = publisher()
    unknown = next(n for n in range(1, 256) if pub._channel_resolver.resolve(n, Protocol.MESHTASTIC).startswith("ch"))
    assert not pub.publish(packet(channel_hash=unknown))
    config.enabled = False
    assert not pub.publish(packet())
    client.publish.assert_not_called()


def test_allowlisting_legacy_dm_channel_does_not_grant_dm_permission():
    pub, client, _ = publisher()
    channel = next(n for n in range(1, 256) if pub._channel_resolver.resolve(n, Protocol.MESHTASTIC) == "LongFast")
    assert pub.publish(packet(channel_hash=channel))
    client.reset_mock()
    assert not pub.publish(packet(channel_hash=channel, destination_id="55667788"))
    client.publish.assert_not_called()


def test_undecrypted_broadcast_stays_blocked():
    pub, client, _ = publisher()
    assert not pub.publish(packet(decrypted=False, encrypted_payload=b"synthetic ciphertext"))
    assert not pub.publish(packet(packet_type=PacketType.ENCRYPTED))
    client.publish.assert_not_called()


def test_privacy_blocks_are_observable_without_message_details(caplog, monkeypatch):
    monkeypatch.setattr(module.time, "monotonic", lambda: 100)
    pub, _, _ = publisher()
    with caplog.at_level("INFO", logger=module.__name__):
        for _ in range(2):
            pub.publish(packet(destination_id="55667788", decoded_payload={"text": "private canary"}))
        assert len(caplog.records) == 1
        monkeypatch.setattr(module.time, "monotonic", lambda: 161)
        pub.publish(packet(destination_id="55667788"))
    assert len(caplog.records) == 2
    assert pub.get_runtime_status()["blocked_destination_count"] == 3
    assert "55667788" not in caplog.text and "private canary" not in caplog.text


def test_real_pki_decode_keeps_dm_local():
    from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
    from src.decode.crypto_service import CryptoService
    from src.decode.meshtastic_decoder import MeshtasticDecoder
    from src.decode.pki_crypto import encrypt_pki_payload

    sender, receiver = X25519PrivateKey.generate(), X25519PrivateKey.generate()
    source, destination, packet_id = 0x11223344, 0x55667788, 0x12345678
    crypto = CryptoService(default_key_b64="")
    crypto.set_keypair(receiver.private_bytes_raw(), receiver.public_key().public_bytes_raw())
    crypto.register_public_key(source, sender.public_key().public_bytes_raw())
    inner = Data(portnum=1, payload=b"synthetic private message").SerializeToString()
    ciphertext = encrypt_pki_payload(inner, private_key=sender.private_bytes_raw(),
                                    remote_public_key=receiver.public_key().public_bytes_raw(),
                                    from_node_id=source, packet_id=packet_id)
    decoder = MeshtasticDecoder(crypto)
    decoder.configure_identity(destination)
    decoded = decoder.decode(struct.pack("<IIIBBBB", destination, source, packet_id, 0x63, 0, 0, 0) + ciphertext)
    assert decoded.decrypted and decoded.packet_type == PacketType.TEXT
    assert decoded.channel_hash == 0 and decoded.encrypted_payload is None
    pub, client, _ = publisher()
    assert not pub.publish(decoded)
    client.publish.assert_not_called()
    assert decoded.decoded_payload["text"] == "synthetic private message"


def test_meshcore_contact_adapter_cannot_publish_dm():
    from src.decode.meshcore_event_adapter import _build_contact_message
    dm = _build_contact_message({"text": "synthetic DM", "pubkey_prefix": "aabbccdd"}, None)
    pub, client, _ = publisher()
    assert not pub.publish(dm)
    client.publish.assert_not_called()


@pytest.mark.parametrize("precision", ["exact", "approximate", "none"])
@pytest.mark.parametrize("protocol", [Protocol.MESHTASTIC, Protocol.MESHCORE])
def test_location_policy_covers_all_outputs_and_retained_state(precision, protocol):
    data = {"latitude": 12.3456789, "longitude": 23.4567891, "altitude": 123, "precision_bits": 32}
    original = packet(protocol=protocol, destination_id="ffffffff" if protocol == Protocol.MESHTASTIC else "broadcast",
                      packet_type=PacketType.POSITION, decoded_payload=data,
                      raw_app_payload=b"original data", raw_radio_packet=b"original frame")
    before = deepcopy(original)
    pub, client, _ = publisher(location_precision=precision)
    pub.publish(original)
    assert original == before
    assert original.decoded_payload is data
    calls = {c.args[0]: (c.args[1], c.kwargs) for c in client.publish.call_args_list}
    state, options = next(v for k, v in calls.items() if k.endswith("/position"))
    assert options["retain"] is True
    if precision == "none":
        assert state == b""
        assert not any("/2/e/" in k for k in calls)
    else:
        expected = 12.3456789 if precision == "exact" else 12.35
        assert json.loads(state)["latitude"] == expected
        if protocol == Protocol.MESHTASTIC:
            blob = next(v[0] for k, v in calls.items() if "/2/e/" in k)
            decoded = Position.FromString(ServiceEnvelope.FromString(blob).packet.decoded.payload)
            assert decoded.latitude_i == round(expected * 1e7)
    for topic, (body, _) in calls.items():
        if "/2/json/" in topic or "/2/c/" in topic:
            payload = json.loads(body).get("payload", {})
            if precision == "none":
                assert not {"latitude", "longitude", "altitude", "precision_bits"} & payload.keys()
            else:
                assert payload["latitude"] == expected


def test_hidden_position_clears_retained_state_without_json_mirror():
    pub, client, _ = publisher(location_precision="none", publish_json=False)
    pub.publish(packet(packet_type=PacketType.POSITION, decoded_payload={"latitude": 1.2, "longitude": 3.4}))
    client.publish.assert_called_once_with("meshpoint/11223344/position", b"", qos=1, retain=True)


@pytest.mark.parametrize("data", [{"longitude": 1.12345}, {"latitude": None, "longitude": 1.12345},
                                  {"latitude": float("nan"), "longitude": 1},
                                  {"latitude": True, "longitude": 1},
                                  {"latitude": 91, "longitude": 1},
                                  {"latitude": "1.2", "longitude": 3}])
@pytest.mark.parametrize("precision", ["exact", "approximate", "none"])
def test_partial_or_invalid_coordinates_fail_closed(data, precision):
    sanitized = prepare_packet(packet(decoded_payload=data), precision)
    assert "latitude" not in sanitized.decoded_payload
    assert "longitude" not in sanitized.decoded_payload


def test_nested_location_and_raw_packet_copies_are_sanitized():
    data = {"temperature": 21, "positions": [{"latitude": 1.234567, "longitude": 2.345678,
             "latitude_i": 12345670, "longitude_i": 23456780, "altitude": 200}]}
    original = packet(decoded_payload=data, raw_app_payload=b"raw", raw_radio_packet=b"frame")
    hidden = prepare_packet(original, "none")
    assert hidden.decoded_payload == {"temperature": 21, "positions": [{}]}
    approximate = prepare_packet(original, "approximate")
    assert approximate.decoded_payload["positions"] == [{"latitude": 1.23, "longitude": 2.35}]
    assert hidden.raw_app_payload is None and hidden.raw_radio_packet is None
    assert original.raw_app_payload == b"raw" and data["positions"][0]["altitude"] == 200


def test_precision_changes_are_used_by_every_output_without_formatter_recreation():
    pub, client, config = publisher(location_precision="exact")
    position = packet(packet_type=PacketType.POSITION, decoded_payload={"latitude": 12.3456789, "longitude": 23.4567891})
    for precision in ("approximate", "none", "exact"):
        config.location_precision = precision
        client.reset_mock()
        pub.publish(position)
        body = next(c.args[1] for c in client.publish.call_args_list if "/2/json/" in c.args[0])
        payload = json.loads(body).get("payload", {})
        assert payload.get("latitude") == {"approximate": 12.35, "none": None, "exact": 12.3456789}[precision]
