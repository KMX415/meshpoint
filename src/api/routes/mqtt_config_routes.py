"""MQTT settings for the Configuration panel.

Maps the dashboard's ``mqtt_card.js`` field names (``broker_host``,
``region_segment``, ``encrypted``, etc.) to the ``mqtt:`` block in
``local.yaml`` and the runtime :class:`~src.config.MqttConfig`.
"""

from __future__ import annotations

import logging
import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from src.api.audit import AuditLogWriter
from src.api.audit.dependencies import get_audit_writer
from src.api.auth.dependencies import require_admin
from src.api.auth.jwt_session import SessionClaims
from src.config import AppConfig, MqttConfig, save_section_to_yaml
from src.relay.mqtt_publisher import _resolve_gateway_id

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/config", tags=["config"])

_config: AppConfig | None = None

_GATEWAY_RE = re.compile(r"^!?[0-9a-fA-F]{8}$")


def init_routes(config: AppConfig) -> None:
    global _config
    _config = config


def reset_routes() -> None:
    global _config
    _config = None


def build_mqtt_status(mqtt: MqttConfig, device_name: str) -> dict:
    """Shape consumed by ``frontend/js/configuration/mqtt_card.js``."""
    gateway = _resolve_gateway_id(mqtt.gateway_id, device_name or "meshpoint")
    return {
        "enabled": mqtt.enabled,
        "broker_host": mqtt.broker,
        "broker_port": mqtt.port,
        "topic_root": mqtt.topic_root,
        "region_segment": mqtt.region,
        "encrypted": not mqtt.publish_json,
        "gateway_id": gateway,
    }


class MqttUpdate(BaseModel):
    enabled: bool = False
    broker_host: str = ""
    broker_port: int = Field(1883, ge=1, le=65535)
    topic_root: str = "msh"
    region_segment: str = "US"
    encrypted: bool = True
    gateway_id: str = ""


@router.put("/mqtt")
async def update_mqtt(
    req: MqttUpdate,
    _claims: SessionClaims = Depends(require_admin),
    audit: AuditLogWriter = Depends(get_audit_writer),
):
    """Persist MQTT broker and topic settings. Requires service restart."""
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

    updates = {
        "enabled": req.enabled,
        "broker": broker,
        "port": req.broker_port,
        "topic_root": topic_root,
        "region": region,
        "publish_json": not req.encrypted,
        "gateway_id": gateway_override or None,
    }

    with audit.timed_action(
        user=_claims.subject,
        action="config.mqtt_update",
        params={
            "enabled": req.enabled,
            "broker": broker,
            "port": req.broker_port,
            "topic_root": topic_root,
            "region": region,
        },
    ):
        mqtt = _config.mqtt
        mqtt.enabled = updates["enabled"]
        mqtt.broker = updates["broker"]
        mqtt.port = updates["port"]
        mqtt.topic_root = updates["topic_root"]
        mqtt.region = updates["region"]
        mqtt.publish_json = updates["publish_json"]
        mqtt.gateway_id = updates["gateway_id"]

        try:
            save_section_to_yaml("mqtt", updates)
        except PermissionError as exc:
            raise HTTPException(403, str(exc)) from exc

    device_name = _config.device.device_name or "meshpoint"
    logger.info(
        "MQTT config updated: enabled=%s broker=%s:%s prefix=%s/%s/2/%s",
        req.enabled,
        broker,
        req.broker_port,
        topic_root,
        region,
        "e" if req.encrypted else "json",
    )

    return {
        "saved": True,
        "restart_required": True,
        "mqtt": build_mqtt_status(mqtt, device_name),
    }
