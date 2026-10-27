"""Initial PiMesh configuration. Reinstallation preserves existing identities."""

import json
import os
import secrets
import sys
import uuid
from pathlib import Path

import yaml


def provision(board, band, region, protocol, revision, root=Path("/")):
    if board not in ("pimesh-v1", "pimesh-v2") or band not in ("868", "915"):
        raise ValueError("Unknown PiMesh profile")
    if protocol not in ("meshtastic", "meshcore") or region not in (
        "US",
        "EU_868",
        "ANZ",
    ):
        raise ValueError("Unknown protocol or region")
    marker = root / "etc/meshpoint/pimesh.json"
    if marker.exists():
        old = json.loads(marker.read_text())
        if old.get("board") != board or old.get("band") != band:
            raise ValueError(
                "Existing board/band differs; explicit hardware migration required"
            )
    profiles = json.loads(
        (root / "opt/meshpoint-openhop/radio-settings.json").read_text()
    )
    hardware = profiles["hardware"][board.replace("pimesh-", "pimesh-1w-")].copy()
    hardware.pop("name", None)
    from importlib.util import module_from_spec, spec_from_file_location

    spec = spec_from_file_location(
        "mc_presets", root / "opt/meshpoint/src/cli/meshcore_radio_config.py"
    )
    module = module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    preset = module.REGION_PRESETS[
        {"US": "USA_CANADA", "EU_868": "EU_UK_NARROW", "ANZ": "AUSTRALIA"}[region]
    ]
    config_path = root / "etc/meshpoint-openhop/config.yaml"
    if not config_path.exists():
        cfg = {
            "radio_type": "sx1262",
            "sx1262": hardware,
            "radio": {
                "frequency": int(preset.frequency_mhz * 1e6),
                "bandwidth": int(preset.bandwidth_khz * 1000),
                "spreading_factor": preset.spreading_factor,
                "coding_rate": preset.coding_rate,
                "tx_power": 18,
                "preamble_length": 32,
            },
            "repeater": {
                "node_name": "Meshpoint",
                "mode": "monitor",
                "send_advert_interval_hours": 0,
                "allow_discovery": False,
                "security": {
                    "admin_password": secrets.token_urlsafe(32),
                    "guest_password": secrets.token_urlsafe(32),
                    "allow_read_only": False,
                },
            },
            "identities": {
                "companions": [
                    {
                        "name": "Meshpoint",
                        "identity_key": secrets.token_hex(32),
                        "settings": {
                            "node_name": "Meshpoint",
                            "tcp_port": 5000,
                            "bind_address": "127.0.0.1",
                            "tcp_timeout": 0,
                        },
                    }
                ]
            },
            "storage": {"storage_dir": "/var/lib/meshpoint-openhop"},
            "http": {"enabled": True, "host": "127.0.0.1", "port": 8000},
            "gps": {"enabled": False},
            "sensors": {"enabled": False},
            "mqtt_brokers": {"brokers": []},
            "logging": {"level": "WARNING"},
        }
        config_path.write_text(yaml.safe_dump(cfg))
        credential = root / "opt/meshpoint/config/openhop-auth.json"
        credential.write_text(
            json.dumps({"password": cfg["repeater"]["security"]["admin_password"]})
        )
        os.chmod(credential, 0o600)
    local = root / "opt/meshpoint/config/local.yaml"
    cfg = yaml.safe_load(local.read_text()) if local.exists() else {}
    cfg = cfg or {}
    cfg.setdefault("device", {}).update(
        platform="node",
        radio_hat=board,
        hardware_description="MeshSmith PiMesh-1W " + board[-2:].upper(),
    )
    if not cfg["device"].get("device_id"):
        cfg["device"]["device_id"] = str(uuid.uuid4())
    cfg.setdefault("radio", {}).setdefault("region", region)
    cfg.setdefault("transmit", {}).setdefault("enabled", True)
    cfg.setdefault("capture", {})["sources"] = (
        ["meshtasticd"] if protocol == "meshtastic" else ["meshcore_usb"]
    )
    local.write_text(yaml.safe_dump(cfg, sort_keys=False))
    os.chmod(local, 0o600)
    state = root / "var/lib/meshpoint-radio/state.json"
    if not state.exists():
        state.write_text(
            json.dumps(
                {
                    "phase": "ready",
                    "active": protocol,
                    "last_good": protocol,
                    "target": None,
                    "operation_id": "initial",
                    "error": "",
                }
            )
        )
    marker.write_text(
        json.dumps(
            {
                "schema": 1,
                "board": board,
                "band": band,
                "region": region,
                "openhop_revision": revision,
            }
        )
    )


if __name__ == "__main__":
    provision(*sys.argv[1:])
