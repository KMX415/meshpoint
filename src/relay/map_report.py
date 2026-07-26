"""Native Meshtastic MQTT map-report construction.

Map reports are synthetic MQTT-only packets. They are never transmitted over
LoRa, and they deliberately use the configured Meshpoint node identity rather
than the separate MQTT gateway identity.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.relay.mqtt_formatter import MqttMessage, _build_topic_prefix

MAP_REPORT_PORTNUM = 73
BROADCAST_NODE_ID = 0xFFFFFFFF
MIN_POSITION_PRECISION = 12
MAX_POSITION_PRECISION = 15
DEFAULT_POSITION_PRECISION = 14


@dataclass(frozen=True)
class MapReportData:
    """Values published in a Meshtastic ``MapReport`` protobuf."""

    node_id: int
    long_name: str
    short_name: str
    latitude: float
    longitude: float
    altitude: float | None
    firmware_version: str
    region: str
    modem_preset: str
    primary_channel_name: str
    has_default_channel: bool
    num_online_local_nodes: int = 0
    position_precision: int = DEFAULT_POSITION_PRECISION
    role: int = 0
    hw_model: int = 37


def build_map_report_message(
    data: MapReportData,
    *,
    topic_root: str,
    mqtt_region: str,
) -> MqttMessage:
    """Build the official ``ServiceEnvelope`` published on ``/2/map/``."""
    from meshtastic.protobuf import mesh_pb2, mqtt_pb2

    precision = max(
        MIN_POSITION_PRECISION,
        min(int(data.position_precision), MAX_POSITION_PRECISION),
    )
    node_id = int(data.node_id) & 0xFFFFFFFF
    node_id_text = f"!{node_id:08x}"

    report = mqtt_pb2.MapReport()
    report.long_name = data.long_name[:24]
    report.short_name = data.short_name[:4]
    report.role = int(data.role)
    report.hw_model = int(data.hw_model)
    report.firmware_version = data.firmware_version[:17]
    report.region = _enum_value(
        "meshtastic.protobuf.config_pb2",
        "Config.LoRaConfig.RegionCode",
        data.region,
    )
    report.modem_preset = _enum_value(
        "meshtastic.protobuf.config_pb2",
        "Config.LoRaConfig.ModemPreset",
        data.modem_preset,
    )
    report.has_default_channel = bool(data.has_default_channel)
    report.latitude_i = _round_coordinate(data.latitude, precision)
    report.longitude_i = _round_coordinate(data.longitude, precision)
    if data.altitude is not None:
        report.altitude = int(data.altitude)
    report.position_precision = precision
    report.num_online_local_nodes = max(
        0, min(int(data.num_online_local_nodes), 0xFFFF)
    )
    report.has_opted_report_location = True

    mesh_packet = mesh_pb2.MeshPacket()
    setattr(mesh_packet, "from", node_id)
    mesh_packet.to = BROADCAST_NODE_ID
    mesh_packet.decoded.portnum = MAP_REPORT_PORTNUM
    mesh_packet.decoded.payload = report.SerializeToString()

    envelope = mqtt_pb2.ServiceEnvelope()
    envelope.packet.CopyFrom(mesh_packet)
    envelope.channel_id = data.primary_channel_name
    envelope.gateway_id = node_id_text

    prefix = _build_topic_prefix(topic_root, mqtt_region)
    return MqttMessage(
        topic=f"{prefix}/2/map/",
        payload=envelope.SerializeToString(),
    )


def _round_coordinate(degrees: float, precision: int) -> int:
    """Match the bit masking and half-step offset used by Meshtastic firmware."""
    value = int(float(degrees) * 1e7)
    unsigned = value & 0xFFFFFFFF
    mask = (0xFFFFFFFF << (32 - precision)) & 0xFFFFFFFF
    rounded = ((unsigned & mask) + (1 << (31 - precision))) & 0xFFFFFFFF
    if rounded >= 0x80000000:
        return rounded - 0x100000000
    return rounded


def _enum_value(module_name: str, enum_path: str, name: str) -> int:
    """Resolve generated protobuf enum names without hard-coded numbers."""
    from importlib import import_module

    value = import_module(module_name)
    for part in enum_path.split("."):
        value = getattr(value, part)
    try:
        return int(value.Value(name))
    except ValueError:
        return 0
