"""Reticulum settings persisted for the next isolated worker restart.

Interface changes apply after restarting Meshpoint through its existing admin
restart endpoint. No system-wide rnsd service or installer helper is used.
"""

from __future__ import annotations

import re
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator, model_validator

from src.api.audit import AuditLogWriter
from src.api.audit.dependencies import get_audit_writer
from src.api.auth.dependencies import require_admin
from src.api.auth.jwt_session import SessionClaims

from . import state

router = APIRouter(prefix="/api/config", tags=["config", "reticulum"])

# SX127x/SX126x (every RNode board) only accept these LoRa bandwidths --
# anything else silently fails to key up, so reject early rather than let a
# typo reach rnsd only to be discovered on the next restart.
_VALID_BANDWIDTHS_HZ = frozenset(
    {7800, 10400, 15600, 20800, 31250, 41700, 62500, 125000, 250000, 500000}
)


def _clean_dest_hash(value: str) -> str | None:
    """Normalise one Reticulum destination hash. Tolerates the shapes
    users actually paste -- a bare hex hash, or RNS's ``<hex>`` / ``aa:bb``
    display forms (the startup banner + "You:" line use ``<hex>``).
    Returns the cleaned hash, ``""`` for blank, or ``None`` if malformed."""
    stripped = str(value or "").strip().lower().replace(":", "").strip("<>")
    if not stripped:
        return ""
    if (
        len(stripped) < 8 or len(stripped) > 64 or len(stripped) % 2
        or any(c not in "0123456789abcdef" for c in stripped)
    ):
        return None
    return stripped


_RESERVED_IFACE_NAMES = {"default interface", "rnode lora", "reticulumnet internet"}


class ExtraInterface(BaseModel):
    """One operator-added RNS interface. Only the three types the UI
    offers; type-specific fields are validated in the model validator."""

    name: str = Field(..., min_length=1, max_length=48)
    type: Literal["TCPClientInterface", "TCPServerInterface", "UDPInterface"]
    enabled: bool = True
    target_host: str = ""
    target_port: int = Field(0, ge=0, le=65535)
    listen_ip: str = ""
    listen_port: int = Field(0, ge=0, le=65535)
    forward_ip: str = ""
    forward_port: int = Field(0, ge=0, le=65535)

    @field_validator("name")
    @classmethod
    def _name_ok(cls, value: str) -> str:
        cleaned = value.strip().replace("[", "").replace("]", "").strip()
        if not cleaned:
            raise ValueError("interface name is required")
        if cleaned.lower() in _RESERVED_IFACE_NAMES:
            raise ValueError(f"'{cleaned}' is a reserved interface name")
        return cleaned

    @model_validator(mode="after")
    def _type_fields_present(self) -> "ExtraInterface":
        if self.type == "TCPClientInterface":
            if not self.target_host.strip():
                raise ValueError(f"{self.name}: TCPClientInterface needs a target host")
            if not 1 <= self.target_port <= 65535:
                raise ValueError(f"{self.name}: TCPClientInterface needs a target port")
        elif self.type in ("TCPServerInterface", "UDPInterface"):
            if not 1 <= self.listen_port <= 65535:
                raise ValueError(f"{self.name}: {self.type} needs a listen port")
        return self

    def to_stored(self) -> dict:
        """Only the fields this type actually uses -- keeps local.yaml tidy
        and matches what write_rnsd_config.py reads back."""
        base = {"name": self.name, "type": self.type, "enabled": self.enabled}
        if self.type == "TCPClientInterface":
            base["target_host"] = self.target_host.strip()
            base["target_port"] = self.target_port
        elif self.type == "TCPServerInterface":
            base["listen_ip"] = self.listen_ip.strip() or "0.0.0.0"
            base["listen_port"] = self.listen_port
        elif self.type == "UDPInterface":
            base["listen_ip"] = self.listen_ip.strip() or "0.0.0.0"
            base["listen_port"] = self.listen_port
            base["forward_ip"] = self.forward_ip.strip() or "255.255.255.255"
            base["forward_port"] = self.forward_port or self.listen_port
        return base


class ReticulumUpdate(BaseModel):
    display_name: str = "Meshpoint"
    nomad_timeout_s: int = Field(20, ge=5, le=120)
    node_enabled: bool = False
    node_name: str = ""
    node_pages_dir: str = "data/reticulum/pages"
    node_announce_interval_s: int = Field(21600, ge=600, le=604800)
    node_spaceapi_url: str = ""
    node_events_ical_url: str = ""
    talkback_enabled: bool = False
    notify_url: str = ""
    propagation_enabled: bool = False
    propagation_storage_limit_mb: int = Field(250, ge=0, le=100_000)
    propagation_outbound_node: str = ""
    propagation_auto_sync_interval_s: int = Field(0, ge=0, le=86_400)
    telemetry_enabled: bool = False
    telemetry_collector: str = ""
    telemetry_interval_s: int = Field(900, ge=300, le=86_400)
    telemetry_include_location: bool = False
    rnode_enabled: bool = False
    rnode_serial_port: str = ""
    rnode_frequency_hz: int | None = Field(None, ge=100_000_000, le=1_000_000_000)
    rnode_bandwidth_hz: int = 125_000
    rnode_tx_power: int = Field(7, ge=0, le=22)
    rnode_spreading_factor: int = Field(7, ge=5, le=12)
    rnode_coding_rate: int = Field(5, ge=5, le=8)
    rnode_airtime_limit_short: float | None = Field(None, gt=0, le=100, allow_inf_nan=False)
    rnode_airtime_limit_long: float | None = Field(None, gt=0, le=100, allow_inf_nan=False)
    backbone_enabled: bool = False
    backbone_host: str = ""
    backbone_port: int = Field(4242, ge=1, le=65535)
    extra_interfaces: list[ExtraInterface] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def _enabled_radio_needs_frequency(self):
        if self.rnode_enabled and self.rnode_frequency_hz is None:
            raise ValueError("Choose an RNode frequency for this region before enabling RF")
        return self

    @field_validator("rnode_bandwidth_hz")
    @classmethod
    def _check_bandwidth(cls, value: int) -> int:
        if value not in _VALID_BANDWIDTHS_HZ:
            allowed = ", ".join(str(v) for v in sorted(_VALID_BANDWIDTHS_HZ))
            raise ValueError(f"rnode_bandwidth_hz must be one of: {allowed}")
        return value

    @field_validator("display_name")
    @classmethod
    def _non_empty(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("must not be empty")
        return stripped

    @field_validator("node_spaceapi_url", "node_events_ical_url", "notify_url")
    @classmethod
    def _feed_url_ok(cls, value: str) -> str:
        stripped = value.strip()
        if stripped and not stripped.startswith(("http://", "https://")):
            raise ValueError("must be an http(s) URL or blank")
        return stripped

    @field_validator("propagation_outbound_node")
    @classmethod
    def _dest_hash_ok(cls, value: str) -> str:
        cleaned = _clean_dest_hash(value)
        if cleaned is None:
            raise ValueError(
                "must be a Reticulum destination hash (hex, e.g. the 32-char "
                "hash from a peer's Destination column) or blank"
            )
        return cleaned

    @field_validator("telemetry_collector")
    @classmethod
    def _collector_hashes_ok(cls, value: str) -> str:
        # A textarea: one address per line (commas / extra whitespace also
        # accepted). Normalise each, drop blanks/dupes, re-join one per line.
        out: list[str] = []
        seen: set = set()
        for token in re.split(r"[\s,]+", value or ""):
            if not token:
                continue
            cleaned = _clean_dest_hash(token)
            if not cleaned:
                raise ValueError(f"{token!r} is not a valid Reticulum destination hash")
            if cleaned not in seen:
                seen.add(cleaned)
                out.append(cleaned)
        return "\n".join(out)

    @model_validator(mode="after")
    def _extra_interface_names_unique(self) -> "ReticulumUpdate":
        names = [i.name.strip().lower() for i in self.extra_interfaces]
        if len(names) != len(set(names)):
            raise ValueError("extra interface names must be unique")
        return self

    @model_validator(mode="after")
    def _auto_sync_needs_a_node(self) -> "ReticulumUpdate":
        if self.propagation_auto_sync_interval_s and not self.propagation_outbound_node:
            raise ValueError(
                "Auto-sync needs an outbound propagation node -- set one, or "
                "leave the interval at 0 for manual sync only"
            )
        if 0 < self.propagation_auto_sync_interval_s < 300:
            raise ValueError("propagation_auto_sync_interval_s must be 0 or at least 300")
        return self

    @model_validator(mode="after")
    def _telemetry_needs_a_collector(self) -> "ReticulumUpdate":
        if self.telemetry_enabled and not self.telemetry_collector:
            raise ValueError(
                "Telemetry publishing needs a collector address -- set one, or "
                "turn telemetry off"
            )
        return self

    @model_validator(mode="after")
    def _talkback_needs_node(self) -> "ReticulumUpdate":
        if self.talkback_enabled and not self.node_enabled:
            raise ValueError(
                "The talk-back bot answers from data the hosted NomadNet "
                "node caches -- enable \"Host a NomadNet node\" first"
            )
        return self


@router.get("/reticulum")
async def get_reticulum(_claims: SessionClaims = Depends(require_admin)):
    """Current ``plugins.reticulum.*`` values for the Settings tab to load.
    ``enabled`` is deliberately not here -- Settings -> Plugins owns it."""
    return state.to_dict()


@router.put("/reticulum")
async def update_reticulum(
    req: ReticulumUpdate,
    claims: SessionClaims = Depends(require_admin),
    audit: AuditLogWriter = Depends(get_audit_writer),
):
    pages_dir = state.to_dict().get("node_pages_dir", "data/reticulum/pages")
    if "node_pages_dir" in req.model_fields_set and req.node_pages_dir.strip() != pages_dir:
        raise HTTPException(422, "The page directory is managed by Meshpoint")
    updates = {
        "display_name": req.display_name,
        "nomad_timeout_s": req.nomad_timeout_s,
        "node_enabled": req.node_enabled,
        "node_name": req.node_name.strip(),
        "node_pages_dir": pages_dir,
        "node_announce_interval_s": req.node_announce_interval_s,
        "node_spaceapi_url": req.node_spaceapi_url.strip(),
        "node_events_ical_url": req.node_events_ical_url.strip(),
        "talkback_enabled": req.talkback_enabled,
        "notify_url": req.notify_url.strip(),
        "propagation_enabled": req.propagation_enabled,
        "propagation_storage_limit_mb": req.propagation_storage_limit_mb,
        "propagation_outbound_node": req.propagation_outbound_node,
        "propagation_auto_sync_interval_s": req.propagation_auto_sync_interval_s,
        "telemetry_enabled": req.telemetry_enabled,
        "telemetry_collector": req.telemetry_collector,
        "telemetry_interval_s": req.telemetry_interval_s,
        "telemetry_include_location": req.telemetry_include_location,
        "rnode_enabled": req.rnode_enabled,
        "rnode_serial_port": req.rnode_serial_port.strip(),
        "rnode_frequency_hz": req.rnode_frequency_hz,
        "rnode_bandwidth_hz": req.rnode_bandwidth_hz,
        "rnode_tx_power": req.rnode_tx_power,
        "rnode_spreading_factor": req.rnode_spreading_factor,
        "rnode_coding_rate": req.rnode_coding_rate,
        "rnode_airtime_limit_short": req.rnode_airtime_limit_short,
        "rnode_airtime_limit_long": req.rnode_airtime_limit_long,
        "backbone_enabled": req.backbone_enabled,
        "backbone_host": req.backbone_host,
        "backbone_port": req.backbone_port,
        "extra_interfaces": [i.to_stored() for i in req.extra_interfaces],
    }
    from .rns_config import render_config
    try:
        render_config(updates)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    with audit.timed_action(
        user=claims.subject,
        action="config.reticulum_update",
        params={k: v for k, v in updates.items() if k != "rnode_serial_port"},
    ):
        try:
            state.set_config(updates)
        except PermissionError as exc:
            raise HTTPException(403, str(exc)) from exc

    # nomad_timeout_s takes effect immediately -- the rest need a restart.
    from . import nomad
    nomad.set_timeouts(req.nomad_timeout_s)
    return {"saved": True, "restart_required": True}


@router.post("/reticulum/restart-rnsd")
async def restart_rnsd(_claims: SessionClaims = Depends(require_admin)):
    """The managed daemon shares Meshpoint's lifecycle; no sudo service calls."""
    return {"success": False, "restart_required": True,
            "output": "Settings saved. Restart Meshpoint to apply Reticulum interface changes."}
