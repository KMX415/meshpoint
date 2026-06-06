"""Protocol-specific MQTT topic and payload formatters.

Meshtastic: ServiceEnvelope protobuf on msh/<region>/2/e/<channel>/<node_id>
MeshCore:   JSON payload on msh/<region>/2/c/<channel>/<node_id>
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Optional

from src.models.packet import Packet, PacketType
from src.relay.channel_resolver import ChannelResolver
from src.hal.location.privacy import LocationPrivacy as LocationRounder

logger = logging.getLogger(__name__)

PORTNUM_MAP = {
    PacketType.TEXT: 1,
    PacketType.POSITION: 3,
    PacketType.NODEINFO: 4,
    PacketType.ROUTING: 5,
    PacketType.TELEMETRY: 67,
    PacketType.TRACEROUTE: 70,
    PacketType.NEIGHBORINFO: 71,
    PacketType.MAP_REPORT: 73,
    PacketType.WAYPOINT: 8,
    PacketType.DETECTION_SENSOR: 49,
    PacketType.PAXCOUNTER: 51,
    PacketType.RANGE_TEST: 69,
    PacketType.STORE_FORWARD: 56,
    PacketType.ADMIN: 6,
}


@dataclass
class MqttMessage:
    topic: str
    payload: bytes


class MeshtasticMqttFormatter:
    """Builds ServiceEnvelope protobuf messages for Meshtastic MQTT.

    Publishes using the decoded payload variant (portnum + payload bytes),
    matching the default Meshtastic firmware behavior. The public broker
    at mqtt.meshtastic.org filters by decoded portnum.
    """

    def __init__(self, topic_root: str, region: str, gateway_id: str,
                 location_precision: str = "exact",
                 channel_resolver: Optional[ChannelResolver] = None):
        self._topic_prefix = _build_topic_prefix(topic_root, region)
        self._gateway_id = gateway_id
        self._location_precision = location_precision
        self._channel_resolver = channel_resolver or ChannelResolver()

    def format(self, packet: Packet) -> Optional[MqttMessage]:
        try:
            from meshtastic.protobuf.mqtt_pb2 import ServiceEnvelope
            from meshtastic.protobuf.mesh_pb2 import MeshPacket
        except ImportError:
            logger.warning("meshtastic protobuf not available")
            return None

        portnum = PORTNUM_MAP.get(packet.packet_type)
        if portnum is None:
            return None

        inner_bytes = _encode_portnum_payload(packet)
        if inner_bytes is None:
            if packet.encrypted_payload:
                return self._format_encrypted(packet)
            return None

        channel_name = self._resolve_channel(packet)
        topic = f"{self._topic_prefix}/2/e/{channel_name}/{self._gateway_id}"

        mesh_pkt = MeshPacket()
        mesh_pkt.id = _parse_packet_id(packet.packet_id)
        mesh_pkt.hop_limit = packet.hop_limit
        mesh_pkt.hop_start = packet.hop_start
        mesh_pkt.want_ack = packet.want_ack
        mesh_pkt.channel = 0

        if packet.source_id and _is_hex(packet.source_id):
            setattr(mesh_pkt, 'from', int(packet.source_id, 16) & 0xFFFFFFFF)
        if packet.destination_id and _is_hex(packet.destination_id):
            mesh_pkt.to = int(packet.destination_id, 16) & 0xFFFFFFFF

        if packet.signal:
            mesh_pkt.rx_rssi = int(packet.signal.rssi)
            mesh_pkt.rx_snr = packet.signal.snr

        mesh_pkt.decoded.portnum = portnum
        mesh_pkt.decoded.payload = inner_bytes

        envelope = ServiceEnvelope()
        envelope.packet.CopyFrom(mesh_pkt)
        envelope.channel_id = channel_name
        envelope.gateway_id = self._gateway_id

        return MqttMessage(topic=topic, payload=envelope.SerializeToString())

    def _format_encrypted(self, packet: Packet) -> Optional[MqttMessage]:
        """Fallback: publish encrypted variant for packets we can't re-encode."""
        try:
            from meshtastic.protobuf.mqtt_pb2 import ServiceEnvelope
            from meshtastic.protobuf.mesh_pb2 import MeshPacket
        except ImportError:
            return None

        channel_name = self._resolve_channel(packet)
        topic = f"{self._topic_prefix}/2/e/{channel_name}/{self._gateway_id}"

        mesh_pkt = MeshPacket()
        mesh_pkt.id = _parse_packet_id(packet.packet_id)
        mesh_pkt.hop_limit = packet.hop_limit
        mesh_pkt.hop_start = packet.hop_start
        mesh_pkt.want_ack = packet.want_ack
        mesh_pkt.channel = packet.channel_hash

        if packet.source_id and _is_hex(packet.source_id):
            setattr(mesh_pkt, 'from', int(packet.source_id, 16) & 0xFFFFFFFF)
        if packet.destination_id and _is_hex(packet.destination_id):
            mesh_pkt.to = int(packet.destination_id, 16) & 0xFFFFFFFF

        mesh_pkt.encrypted = packet.encrypted_payload

        envelope = ServiceEnvelope()
        envelope.packet.CopyFrom(mesh_pkt)
        envelope.channel_id = channel_name
        envelope.gateway_id = self._gateway_id

        return MqttMessage(topic=topic, payload=envelope.SerializeToString())

    def format_json(self, packet: Packet) -> Optional[MqttMessage]:
        """Build a JSON representation on the /json/ topic for HA/Node-RED."""
        channel_name = self._resolve_channel(packet)
        topic = f"{self._topic_prefix}/2/json/{channel_name}/{self._gateway_id}"

        payload = self._build_json_payload(packet)
        return MqttMessage(topic=topic, payload=json.dumps(payload).encode())

    def _build_json_payload(self, packet: Packet) -> dict:
        lat, lon = LocationRounder.apply(
            (packet.decoded_payload or {}).get("latitude"),
            (packet.decoded_payload or {}).get("longitude"),
            self._location_precision,
        )

        result = {
            "id": packet.packet_id,
            "from": packet.source_id,
            "to": packet.destination_id,
            "type": packet.packet_type.value,
            "sender": self._gateway_id,
            "timestamp": int(packet.timestamp.timestamp()),
            "hop_limit": packet.hop_limit,
            "hop_start": packet.hop_start,
        }
        if packet.signal:
            result["rssi"] = packet.signal.rssi
            result["snr"] = packet.signal.snr
        if packet.decoded_payload:
            payload_copy = dict(packet.decoded_payload)
            if lat is not None:
                payload_copy["latitude"] = lat
                payload_copy["longitude"] = lon
            elif "latitude" in payload_copy:
                del payload_copy["latitude"]
                payload_copy.pop("longitude", None)
            result["payload"] = payload_copy
        return result

    def _resolve_channel(self, packet: Packet) -> str:
        return self._channel_resolver.resolve(
            packet.channel_hash, packet.protocol
        )


class MeshCoreMqttFormatter:
    """Builds JSON messages for MeshCore MQTT (meshcore-mqtt compatible)."""

    def __init__(self, topic_root: str, region: str, gateway_id: str,
                 location_precision: str = "exact"):
        self._topic_prefix = _build_topic_prefix(topic_root, region)
        self._gateway_id = gateway_id
        self._location_precision = location_precision

    def format(self, packet: Packet) -> Optional[MqttMessage]:
        channel_name = "MeshCore"
        topic = f"{self._topic_prefix}/2/c/{channel_name}/{self._gateway_id}"

        lat, lon = LocationRounder.apply(
            (packet.decoded_payload or {}).get("latitude"),
            (packet.decoded_payload or {}).get("longitude"),
            self._location_precision,
        )

        payload = {
            "id": packet.packet_id,
            "from": packet.source_id,
            "to": packet.destination_id,
            "type": packet.packet_type.value,
            "sender": self._gateway_id,
            "timestamp": int(packet.timestamp.timestamp()),
        }
        if packet.signal:
            payload["rssi"] = packet.signal.rssi
            payload["snr"] = packet.signal.snr
        if packet.decoded_payload:
            payload_copy = dict(packet.decoded_payload)
            if lat is not None:
                payload_copy["latitude"] = lat
                payload_copy["longitude"] = lon
            elif "latitude" in payload_copy:
                del payload_copy["latitude"]
                payload_copy.pop("longitude", None)
            payload["payload"] = payload_copy

        return MqttMessage(topic=topic, payload=json.dumps(payload).encode())


def _encode_portnum_payload(packet: Packet) -> Optional[bytes]:
    """Re-encode decoded_payload dict back to protobuf bytes for the portnum."""
    if not packet.decoded_payload:
        return None

    data = packet.decoded_payload
    ptype = packet.packet_type

    try:
        if ptype == PacketType.POSITION:
            return _encode_position(data)
        if ptype == PacketType.NODEINFO:
            return _encode_nodeinfo(data)
        if ptype == PacketType.TELEMETRY:
            return _encode_telemetry(data)
        if ptype == PacketType.TEXT:
            text = data.get("text", "")
            return text.encode("utf-8") if text else None
        if ptype == PacketType.ROUTING:
            return _encode_routing(data)
    except Exception:
        logger.debug("Failed to re-encode %s payload", ptype.value)
    return None


def _encode_position(data: dict) -> Optional[bytes]:
    from meshtastic.protobuf.mesh_pb2 import Position
    pos = Position()
    if data.get("latitude") is not None:
        pos.latitude_i = int(data["latitude"] * 1e7)
    if data.get("longitude") is not None:
        pos.longitude_i = int(data["longitude"] * 1e7)
    if data.get("altitude") is not None:
        pos.altitude = int(data["altitude"])
    if data.get("time") is not None:
        pos.time = int(data["time"])
    if data.get("precision_bits") is not None:
        pos.precision_bits = int(data["precision_bits"])
    return pos.SerializeToString()


def _encode_nodeinfo(data: dict) -> Optional[bytes]:
    from meshtastic.protobuf.mesh_pb2 import User
    user = User()
    if data.get("id"):
        user.id = str(data["id"])
    if data.get("long_name"):
        user.long_name = str(data["long_name"])
    if data.get("short_name"):
        user.short_name = str(data["short_name"])
    if data.get("hw_model") is not None:
        user.hw_model = int(data["hw_model"])
    if data.get("role") is not None:
        user.role = int(data["role"])
    return user.SerializeToString()


def _encode_telemetry(data: dict) -> Optional[bytes]:
    from meshtastic.protobuf.telemetry_pb2 import Telemetry
    telem = Telemetry()
    if data.get("time") is not None:
        telem.time = int(data["time"])
    if data.get("battery_level") is not None:
        telem.device_metrics.battery_level = int(data["battery_level"])
    if data.get("voltage") is not None:
        telem.device_metrics.voltage = float(data["voltage"])
    if data.get("channel_utilization") is not None:
        telem.device_metrics.channel_utilization = float(data["channel_utilization"])
    if data.get("air_util_tx") is not None:
        telem.device_metrics.air_util_tx = float(data["air_util_tx"])
    if data.get("temperature") is not None:
        telem.environment_metrics.temperature = float(data["temperature"])
    if data.get("relative_humidity") is not None:
        telem.environment_metrics.relative_humidity = float(data["relative_humidity"])
    if data.get("barometric_pressure") is not None:
        telem.environment_metrics.barometric_pressure = float(data["barometric_pressure"])
    return telem.SerializeToString()


def _encode_routing(data: dict) -> Optional[bytes]:
    from meshtastic.protobuf.mesh_pb2 import Routing
    routing = Routing()
    if data.get("error_reason") is not None:
        routing.error_reason = int(data["error_reason"])
    return routing.SerializeToString()


def _parse_packet_id(packet_id: str) -> int:
    if _is_hex(packet_id):
        return int(packet_id, 16) & 0xFFFFFFFF
    return hash(packet_id) & 0xFFFFFFFF


def _is_hex(value: str) -> bool:
    if not value or value.startswith("!"):
        value = value[1:]
    try:
        int(value, 16)
        return True
    except (ValueError, TypeError):
        return False


def _build_topic_prefix(topic_root: str, region: str) -> str:
    """Build MQTT prefix with backward-compatible root/region semantics.

    Examples:
    - topic_root="msh", region="US"     -> "msh/US"
    - topic_root="msh/US", region="FL"  -> "msh/US/FL"
    - topic_root="msh/US", region="US"  -> "msh/US"  (no duplicate)
    - topic_root="msh", region="US/FL"  -> "msh/US/FL"
    """
    root = (topic_root or "").strip().strip("/")
    reg = (region or "").strip().strip("/")

    if not root and not reg:
        return "msh/US"
    if not reg:
        return root
    if not root:
        return reg

    root_lower = root.lower()
    reg_lower = reg.lower()
    if root_lower == reg_lower or root_lower.endswith(f"/{reg_lower}"):
        return root
    return f"{root}/{reg}"
