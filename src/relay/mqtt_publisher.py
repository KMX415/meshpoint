"""MQTT publisher with two-gate privacy model.

Gate 1: mqtt.enabled must be true (off by default).
Gate 2: only packets from channels listed in publish_channels are published.
         Private/custom channels never leak unless explicitly listed.

Supports dual-protocol publishing (Meshtastic + MeshCore) with optional
JSON mirror for Home Assistant and Node-RED consumers.
"""

from __future__ import annotations

import json
import logging
from typing import Optional

from src.config import MqttConfig
from src.models.packet import Packet, PacketType, Protocol
from src.relay.channel_resolver import ChannelResolver
from src.relay.mqtt_formatter import (
    MeshCoreMqttFormatter,
    MeshtasticMqttFormatter,
    MqttMessage,
)

logger = logging.getLogger(__name__)

try:
    import paho.mqtt.client as paho_mqtt
    from paho.mqtt.client import CallbackAPIVersion
    PAHO_AVAILABLE = True
except ImportError:
    paho_mqtt = None
    CallbackAPIVersion = None
    PAHO_AVAILABLE = False


class MqttPublisher:
    """Publishes decoded packets to an MQTT broker.

    Enforces a two-gate safety model:
      1) MQTT must be explicitly enabled in config
      2) Only packets from whitelisted channels are published
    """

    def __init__(
        self,
        config: MqttConfig,
        device_name: str,
        channel_keys: Optional[dict[str, str]] = None,
    ):
        self._config = config
        self._gateway_id = _resolve_gateway_id(config.gateway_id, device_name)
        self._client: Optional[paho_mqtt.Client] = None
        self._connected = False
        self._publish_count = 0

        self._allowed_channels = set(
            ch.lower() for ch in config.publish_channels
        )

        self._channel_resolver = ChannelResolver(channel_keys=channel_keys)

        self._mt_formatter = MeshtasticMqttFormatter(
            topic_root=config.topic_root,
            region=config.region,
            gateway_id=self._gateway_id,
            location_precision=config.location_precision,
            channel_resolver=self._channel_resolver,
        )
        self._mc_formatter = MeshCoreMqttFormatter(
            topic_root=config.topic_root,
            region=config.region,
            gateway_id=self._gateway_id,
            location_precision=config.location_precision,
        )
        self._ha_discovery: Optional[HomeAssistantDiscovery] = None
        self._topic_prefix = self._resolve_topic_prefix()

    @property
    def gateway_id(self) -> str:
        return self._gateway_id

    @property
    def connected(self) -> bool:
        return self._connected

    @property
    def publish_count(self) -> int:
        return self._publish_count

    def connect(self) -> bool:
        if not PAHO_AVAILABLE:
            logger.error(
                "paho-mqtt not installed. Run: "
                "sudo /opt/meshpoint/venv/bin/pip install paho-mqtt"
            )
            return False

        try:
            session_id = f"meshpoint-{self._gateway_id[1:]}"
            self._client = paho_mqtt.Client(
                CallbackAPIVersion.VERSION1,
                client_id=session_id,
                protocol=paho_mqtt.MQTTv311,
            )
            self._client.on_connect = self._on_connect
            self._client.on_disconnect = self._on_disconnect

            if self._config.username:
                self._client.username_pw_set(
                    self._config.username, self._config.password
                )

            if self._config.tls_enabled:
                ca_path = (self._config.tls_ca_cert or "").strip()
                if ca_path:
                    self._client.tls_set(ca_certs=ca_path)
                else:
                    self._client.tls_set()
                logger.info("MQTT TLS enabled for %s:%d", self._config.broker, self._config.port)

            self._client.connect(
                self._config.broker, self._config.port, keepalive=60
            )
            self._client.loop_start()
            logger.info(
                "MQTT connecting to %s:%d as %s",
                self._config.broker, self._config.port, self._gateway_id,
            )
            logger.info(
                "MQTT topic prefix resolved: %s",
                self._topic_prefix,
            )
            return True
        except Exception:
            logger.exception("MQTT connection failed")
            return False

    def disconnect(self) -> None:
        if self._client:
            self._client.loop_stop()
            self._client.disconnect()
            self._connected = False
            logger.info("MQTT disconnected")

    def publish(self, packet: Packet) -> bool:
        """Publish a packet if it passes the two-gate safety check."""
        if not self._connected or not self._client:
            return False

        if not self._passes_safety_gates(packet):
            return False

        messages = self._format_packet(packet)
        published = False
        for msg in messages:
            result = self._client.publish(msg.topic, msg.payload, qos=1)
            logger.debug("MQTT pub rc=%d topic=%s size=%d", result.rc, msg.topic, len(msg.payload))
            if result.rc == paho_mqtt.MQTT_ERR_SUCCESS:
                published = True

        if published:
            self._publish_count += 1
            logger.debug("MQTT published %s (%s)", packet.packet_id, packet.packet_type.value)
            if self._ha_discovery:
                self._ha_discovery.announce_node(packet)
                self._ha_discovery.publish_state(packet)

        return published

    def _passes_safety_gates(self, packet: Packet) -> bool:
        if packet.packet_type == PacketType.ENCRYPTED:
            return False

        if not packet.decrypted and packet.encrypted_payload:
            return False

        channel_name = self._resolve_channel_name(packet)
        if channel_name.lower() not in self._allowed_channels:
            logger.debug(
                "MQTT gate 2 blocked: channel '%s' not in allowed list", channel_name
            )
            return False

        return True

    def _resolve_channel_name(self, packet: Packet) -> str:
        return self._channel_resolver.resolve(
            packet.channel_hash, packet.protocol
        )

    def _format_packet(self, packet: Packet) -> list[MqttMessage]:
        messages: list[MqttMessage] = []

        if packet.protocol == Protocol.MESHTASTIC:
            msg = self._mt_formatter.format(packet)
            if msg:
                messages.append(msg)
            if self._config.publish_json:
                json_msg = self._mt_formatter.format_json(packet)
                if json_msg:
                    messages.append(json_msg)

        elif packet.protocol == Protocol.MESHCORE:
            msg = self._mc_formatter.format(packet)
            if msg:
                messages.append(msg)

        return messages

    def _on_connect(self, client, userdata, flags, rc) -> None:
        if rc == 0:
            self._connected = True
            logger.info("MQTT publisher started as %s", self._gateway_id)
            logger.debug("MQTT connected to broker=%s", self._config.broker)
            if self._config.homeassistant_discovery and self._client:
                self._ha_discovery = HomeAssistantDiscovery(self._client, self._gateway_id)
        else:
            self._connected = False
            logger.warning("MQTT connection refused (rc=%d)", rc)

    def _on_disconnect(self, client, userdata, rc) -> None:
        self._connected = False
        if rc != 0:
            logger.warning("MQTT unexpected disconnect (rc=%d), auto-reconnecting", rc)

    def _resolve_topic_prefix(self) -> str:
        root = (self._config.topic_root or "").strip().strip("/")
        region = (self._config.region or "").strip().strip("/")
        if not root and not region:
            return "msh/US"
        if not region:
            return root
        if not root:
            return region
        root_lower = root.lower()
        region_lower = region.lower()
        if root_lower == region_lower or root_lower.endswith(f"/{region_lower}"):
            return root
        return f"{root}/{region}"


class HomeAssistantDiscovery:
    """Publishes HA auto-discovery configs for mesh node sensors."""

    DISCOVERY_PREFIX = "homeassistant"

    def __init__(self, client: paho_mqtt.Client, gateway_id: str):
        self._client = client
        self._gateway_id = gateway_id
        self._announced_nodes: set[str] = set()

    def announce_node(self, packet: Packet) -> None:
        if not packet.decoded_payload:
            return

        node_id = packet.source_id
        if node_id in self._announced_nodes:
            return

        payload = packet.decoded_payload
        sensors = []

        if payload.get("battery_level") is not None:
            sensors.append(self._battery_config(node_id))
        if payload.get("temperature") is not None:
            sensors.append(self._temperature_config(node_id))
        if payload.get("latitude") is not None:
            sensors.append(self._gps_tracker_config(node_id))

        for topic, config_payload in sensors:
            self._client.publish(topic, config_payload, qos=1, retain=True)

        if sensors:
            self._announced_nodes.add(node_id)

    def publish_state(self, packet: Packet) -> None:
        """Publish retained state for Home Assistant discovery topics."""
        if not packet.decoded_payload or not packet.source_id:
            return

        node_id = packet.source_id
        payload = packet.decoded_payload

        if packet.packet_type == PacketType.TELEMETRY:
            state = {
                key: payload[key]
                for key in (
                    "battery_level",
                    "temperature",
                    "voltage",
                    "humidity",
                    "barometric_pressure",
                    "channel_utilization",
                    "air_util_tx",
                )
                if key in payload and payload[key] is not None
            }
            if state:
                topic = f"meshpoint/{node_id}/telemetry"
                self._client.publish(
                    topic,
                    json.dumps(state),
                    qos=1,
                    retain=True,
                )
            return

        if packet.packet_type == PacketType.POSITION:
            lat = payload.get("latitude")
            lon = payload.get("longitude")
            if lat is None or lon is None:
                return
            position = {
                "latitude": lat,
                "longitude": lon,
            }
            alt = payload.get("altitude")
            if alt is not None:
                position["altitude"] = alt
            topic = f"meshpoint/{node_id}/position"
            self._client.publish(
                topic,
                json.dumps(position),
                qos=1,
                retain=True,
            )

    def _device_block(self, node_id: str) -> dict:
        return {
            "identifiers": [f"meshpoint_{node_id}"],
            "name": f"Mesh Node {node_id[-4:]}",
            "manufacturer": "Meshtastic",
            "via_device": self._gateway_id,
        }

    def _battery_config(self, node_id: str) -> tuple[str, str]:
        import json
        topic = f"{self.DISCOVERY_PREFIX}/sensor/meshpoint_{node_id}/battery/config"
        config = {
            "name": "Battery",
            "unique_id": f"meshpoint_{node_id}_battery",
            "device": self._device_block(node_id),
            "state_topic": f"meshpoint/{node_id}/telemetry",
            "value_template": "{{ value_json.battery_level }}",
            "unit_of_measurement": "%",
            "device_class": "battery",
        }
        return topic, json.dumps(config)

    def _temperature_config(self, node_id: str) -> tuple[str, str]:
        import json
        topic = f"{self.DISCOVERY_PREFIX}/sensor/meshpoint_{node_id}/temperature/config"
        config = {
            "name": "Temperature",
            "unique_id": f"meshpoint_{node_id}_temperature",
            "device": self._device_block(node_id),
            "state_topic": f"meshpoint/{node_id}/telemetry",
            "value_template": "{{ value_json.temperature }}",
            "unit_of_measurement": "°C",
            "device_class": "temperature",
        }
        return topic, json.dumps(config)

    def _gps_tracker_config(self, node_id: str) -> tuple[str, str]:
        import json
        topic = f"{self.DISCOVERY_PREFIX}/device_tracker/meshpoint_{node_id}/config"
        config = {
            "name": "Location",
            "unique_id": f"meshpoint_{node_id}_tracker",
            "device": self._device_block(node_id),
            "json_attributes_topic": f"meshpoint/{node_id}/position",
            "source_type": "gps",
        }
        return topic, json.dumps(config)


def _resolve_gateway_id(override: Optional[str], device_name: str) -> str:
    """Use explicit config override or derive from device name."""
    if override:
        raw = override.strip()
        if raw.startswith("!"):
            return raw.lower()
        return f"!{raw.lower()}"
    return _generate_gateway_id(device_name)


def _generate_gateway_id(device_name: str) -> str:
    """Deterministic Meshtastic-format gateway ID from device name.

    Format: !XXXXXXXX (8 hex chars) derived from device name hash.
    Broker requires standard node ID format for ServiceEnvelope distribution.
    """
    import hashlib
    digest = hashlib.md5(device_name.lower().encode(), usedforsecurity=False).hexdigest()[:8]  # nosec B324
    return f"!{digest}"
