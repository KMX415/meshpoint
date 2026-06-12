"""MQTT settings for the Configuration panel.

Maps dashboard field names to the ``mqtt:`` block in ``local.yaml`` and
:class:`~src.config.MqttConfig`. Covers the full surface documented in
``docs/MQTT-AND-MESHRADAR.md``.
"""

from __future__ import annotations

import logging
import re
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator

from src.api.audit import AuditLogWriter
from src.api.audit.dependencies import get_audit_writer
from src.api.auth.dependencies import require_admin
from src.api.auth.jwt_session import SessionClaims
from src.config import AppConfig, MqttConfig, save_section_to_yaml
from src.relay.mqtt_publisher import MqttPublisher, _resolve_gateway_id

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/config", tags=["config"])

_config: AppConfig | None = None
_mqtt_publisher: MqttPublisher | None = None

_GATEWAY_RE = re.compile(r"^!?[0-9a-fA-F]{8}$")
_LOCATION_PRECISION = frozenset({"exact", "approximate", "none"})


def init_routes(
    config: AppConfig,
    mqtt_publisher: MqttPublisher | None = None,
) -> None:
    global _config, _mqtt_publisher
    _config = config
    _mqtt_publisher = mqtt_publisher


def reset_routes() -> None:
    global _config, _mqtt_publisher
    _config = None
    _mqtt_publisher = None


def build_mqtt_runtime_status(
    mqtt: MqttConfig,
    publisher: MqttPublisher | None,
) -> dict:
    """Live broker health for the Configuration MQTT card."""
    base = {
        "config_enabled": mqtt.enabled,
        "publisher_active": publisher is not None,
        "connected": False,
        "publish_count": 0,
        "disconnect_count": 0,
        "last_connect_rc": None,
        "last_disconnect_rc": None,
        "last_publish_at": None,
        "connected_since": None,
        "topic_prefix": None,
        "gateway_id": _resolve_gateway_id(mqtt.gateway_id, "meshpoint"),
        "broker_host": mqtt.broker,
        "broker_port": mqtt.port,
    }
    if publisher is None:
        return base
    runtime = publisher.get_runtime_status()
    base.update(runtime)
    base["publisher_active"] = True
    return base


def build_mqtt_status(mqtt: MqttConfig, device_name: str) -> dict:
    """Shape consumed by ``frontend/js/configuration/mqtt_card.js``."""
    gateway = _resolve_gateway_id(mqtt.gateway_id, device_name or "meshpoint")
    return {
        "enabled": mqtt.enabled,
        "broker_host": mqtt.broker,
        "broker_port": mqtt.port,
        "username": mqtt.username,
        "password_set": bool((mqtt.password or "").strip()),
        "topic_root": mqtt.topic_root,
        "region_segment": mqtt.region,
        "gateway_id": gateway,
        "publish_channels": list(mqtt.publish_channels),
        "publish_json": mqtt.publish_json,
        "location_precision": mqtt.location_precision,
        "homeassistant_discovery": mqtt.homeassistant_discovery,
        "tls_enabled": mqtt.tls_enabled,
        "tls_ca_cert": mqtt.tls_ca_cert or "",
        "topic_preview_meshtastic": _topic_example(
            mqtt.topic_root, mqtt.region, "e", "LongFast", gateway
        ),
        "topic_preview_meshcore": _topic_example(
            mqtt.topic_root, mqtt.region, "c", "MeshCore", gateway
        ),
        "topic_preview_json": _topic_example(
            mqtt.topic_root, mqtt.region, "json", "LongFast", gateway
        ),
    }


def _topic_example(
    topic_root: str, region: str, segment: str, channel: str, gateway: str
) -> str:
    root = (topic_root or "msh").strip("/")
    reg = (region or "US").strip("/")
    return f"{root}/{reg}/2/{segment}/{channel}/{gateway}"


class MqttUpdate(BaseModel):
    enabled: bool = False
    broker_host: str = ""
    broker_port: int = Field(1883, ge=1, le=65535)
    username: str = ""
    password: str | None = None
    password_unchanged: bool = True
    topic_root: str = "msh"
    region_segment: str = "US"
    gateway_id: str = ""
    publish_channels: list[str] = Field(default_factory=lambda: ["LongFast"])
    publish_json: bool = False
    location_precision: Literal["exact", "approximate", "none"] = "exact"
    homeassistant_discovery: bool = False
    tls_enabled: bool = False
    tls_ca_cert: str = ""

    @field_validator("publish_channels")
    @classmethod
    def _normalize_channels(cls, channels: list[str]) -> list[str]:
        seen: set[str] = set()
        out: list[str] = []
        for raw in channels:
            name = raw.strip()
            if not name:
                continue
            key = name.lower()
            if key in seen:
                continue
            seen.add(key)
            out.append(name)
        if not out:
            raise ValueError("At least one publish channel is required")
        return out

    @field_validator("location_precision")
    @classmethod
    def _check_precision(cls, value: str) -> str:
        if value not in _LOCATION_PRECISION:
            raise ValueError(
                f"location_precision must be one of: {', '.join(sorted(_LOCATION_PRECISION))}"
            )
        return value


@router.get("/mqtt/runtime")
async def get_mqtt_runtime():
    """Read-only MQTT broker connection health (any authenticated user)."""
    if _config is None:
        raise HTTPException(503, "Config not loaded")
    device_name = _config.device.device_name or "meshpoint"
    payload = build_mqtt_runtime_status(_config.mqtt, _mqtt_publisher)
    payload["gateway_id"] = _resolve_gateway_id(
        _config.mqtt.gateway_id, device_name
    )
    return payload


@router.put("/mqtt")
async def update_mqtt(
    req: MqttUpdate,
    _claims: SessionClaims = Depends(require_admin),
    audit: AuditLogWriter = Depends(get_audit_writer),
):
    """Persist MQTT broker, privacy, and topic settings. Requires service restart."""
    if _config is None:
        raise HTTPException(503, "Config not loaded")

    gateway_override = req.gateway_id.strip()
    if gateway_override and not _GATEWAY_RE.match(gateway_override):
        raise HTTPException(
            400,
            "Gateway ID must be 8 hex digits, optionally prefixed with !",
        )

    broker = req.broker_host.strip() or _config.mqtt.broker
    topic_root = (req.topic_root.strip() or "msh").strip("/")
    region = req.region_segment.strip() or _config.mqtt.region
    username = req.username.strip() or _config.mqtt.username

    updates: dict = {
        "enabled": req.enabled,
        "broker": broker,
        "port": req.broker_port,
        "username": username,
        "topic_root": topic_root,
        "region": region,
        "publish_channels": req.publish_channels,
        "publish_json": req.publish_json,
        "location_precision": req.location_precision,
        "homeassistant_discovery": req.homeassistant_discovery,
        "gateway_id": gateway_override or None,
        "tls_enabled": req.tls_enabled,
        "tls_ca_cert": req.tls_ca_cert.strip(),
    }

    if not req.password_unchanged and req.password is not None:
        updates["password"] = req.password

    with audit.timed_action(
        user=_claims.subject,
        action="config.mqtt_update",
        params={
            "enabled": req.enabled,
            "broker": broker,
            "port": req.broker_port,
            "topic_root": topic_root,
            "region": region,
            "channel_count": len(req.publish_channels),
        },
    ):
        mqtt = _config.mqtt
        mqtt.enabled = updates["enabled"]
        mqtt.broker = updates["broker"]
        mqtt.port = updates["port"]
        mqtt.username = updates["username"]
        mqtt.topic_root = updates["topic_root"]
        mqtt.region = updates["region"]
        mqtt.publish_channels = list(updates["publish_channels"])
        mqtt.publish_json = updates["publish_json"]
        mqtt.location_precision = updates["location_precision"]
        mqtt.homeassistant_discovery = updates["homeassistant_discovery"]
        mqtt.gateway_id = updates["gateway_id"]
        mqtt.tls_enabled = updates["tls_enabled"]
        mqtt.tls_ca_cert = updates["tls_ca_cert"]
        if "password" in updates:
            mqtt.password = updates["password"]

        try:
            save_section_to_yaml("mqtt", updates)
        except PermissionError as exc:
            raise HTTPException(403, str(exc)) from exc

    device_name = _config.device.device_name or "meshpoint"
    logger.info(
        "MQTT config updated: enabled=%s broker=%s:%s channels=%s json=%s ha=%s",
        req.enabled,
        broker,
        req.broker_port,
        len(req.publish_channels),
        req.publish_json,
        req.homeassistant_discovery,
    )

    return {
        "saved": True,
        "restart_required": True,
        "mqtt": build_mqtt_status(mqtt, device_name),
    }
