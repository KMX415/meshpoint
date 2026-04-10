from __future__ import annotations

import dataclasses
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml

from src.version import __version__


@dataclass
class RadioConfig:
    region: str = "US"
    frequency_mhz: float = 906.875
    spreading_factor: int = 11
    bandwidth_khz: float = 250.0
    coding_rate: str = "4/8"
    sync_word: int = 0x2B
    preamble_length: int = 16
    tx_power_dbm: int = 22


@dataclass
class MeshtasticConfig:
    default_key_b64: str = "AQ=="
    channel_keys: dict[str, str] = field(default_factory=dict)


@dataclass
class MeshcoreConfig:
    default_key_b64: str = ""
    channel_keys: dict[str, str] = field(default_factory=dict)


@dataclass
class MeshcoreUsbConfig:
    """MeshCore USB node monitoring -- auto-detected at startup when enabled."""

    serial_port: Optional[str] = None
    baud_rate: int = 115200
    auto_detect: bool = True


@dataclass
class CaptureConfig:
    sources: list[str] = field(default_factory=lambda: ["mock"])
    serial_port: Optional[str] = None
    serial_baud: int = 115200
    concentrator_spi_device: str = "/dev/spidev0.0"
    meshcore_usb: MeshcoreUsbConfig = field(default_factory=MeshcoreUsbConfig)


@dataclass
class StorageConfig:
    database_path: str = "data/concentrator.db"
    max_packets_retained: int = 100_000
    cleanup_interval_seconds: int = 3600


@dataclass
class DashboardConfig:
    host: str = "0.0.0.0"  # nosec B104 -- intentional for local device dashboard
    port: int = 8080
    static_dir: str = "frontend"


@dataclass
class UpstreamConfig:
    enabled: bool = False
    url: str = "wss://api.meshradar.io"
    reconnect_interval_seconds: int = 10
    buffer_max_size: int = 5000
    auth_token: Optional[str] = None


@dataclass
class DeviceConfig:
    device_id: Optional[str] = None
    device_name: str = "Mesh Point"
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    altitude: Optional[float] = None
    hardware_description: str = "RAK2287 + Raspberry Pi 4"
    firmware_version: str = __version__


@dataclass
class RelayConfig:
    enabled: bool = False
    serial_port: Optional[str] = None
    serial_baud: int = 115200
    max_relay_per_minute: int = 20
    burst_size: int = 5
    min_relay_rssi: float = -110.0
    max_relay_rssi: float = -50.0


@dataclass
class MqttConfig:
    enabled: bool = False
    broker: str = "mqtt.meshtastic.org"
    port: int = 1883
    username: str = "meshdev"
    password: str = "large4cats"
    topic_root: str = "msh"
    region: str = "US"
    publish_channels: list[str] = field(default_factory=lambda: ["LongFast", "MeshCore"])
    publish_json: bool = False
    location_precision: str = "exact"
    homeassistant_discovery: bool = False


@dataclass
class TransmitConfig:
    """Native LoRa transmission settings.

    When enabled, the Meshpoint can send Meshtastic messages through
    the onboard SX1261 radio and MeshCore messages through the USB
    companion. Disabled by default: opt-in via local.yaml.
    """

    enabled: bool = False
    node_id: Optional[int] = None
    tx_power_dbm: int = 14
    max_duty_cycle_percent: float = 1.0
    long_name: str = "Mesh Point"
    short_name: str = "MPNT"
    hop_limit: int = 3


@dataclass
class AppConfig:
    radio: RadioConfig = field(default_factory=RadioConfig)
    meshtastic: MeshtasticConfig = field(default_factory=MeshtasticConfig)
    meshcore: MeshcoreConfig = field(default_factory=MeshcoreConfig)
    capture: CaptureConfig = field(default_factory=CaptureConfig)
    storage: StorageConfig = field(default_factory=StorageConfig)
    dashboard: DashboardConfig = field(default_factory=DashboardConfig)
    upstream: UpstreamConfig = field(default_factory=UpstreamConfig)
    device: DeviceConfig = field(default_factory=DeviceConfig)
    relay: RelayConfig = field(default_factory=RelayConfig)
    mqtt: MqttConfig = field(default_factory=MqttConfig)
    transmit: TransmitConfig = field(default_factory=TransmitConfig)


def _merge_dataclass(instance, overrides: dict):
    """Apply dict overrides onto a dataclass instance, merging nested dataclasses."""
    if not overrides:
        return
    for key, value in overrides.items():
        if not hasattr(instance, key):
            continue
        current = getattr(instance, key)
        if dataclasses.is_dataclass(current) and isinstance(value, dict):
            _merge_dataclass(current, value)
        else:
            setattr(instance, key, value)


def _apply_yaml(cfg: AppConfig, path: Path) -> None:
    """Merge a single YAML file into an existing AppConfig."""
    if not path.exists():
        return

    with open(path, "r") as fh:
        raw = yaml.safe_load(fh) or {}

    section_map = {
        "radio": cfg.radio,
        "meshtastic": cfg.meshtastic,
        "meshcore": cfg.meshcore,
        "capture": cfg.capture,
        "storage": cfg.storage,
        "dashboard": cfg.dashboard,
        "upstream": cfg.upstream,
        "device": cfg.device,
        "relay": cfg.relay,
        "mqtt": cfg.mqtt,
        "transmit": cfg.transmit,
    }

    for section_name, section_instance in section_map.items():
        if section_name in raw:
            _merge_dataclass(section_instance, raw[section_name])


_VALID_CONFIG_EXTENSIONS = {".yaml", ".yml"}


def _validated_config_path(raw: str) -> Path:
    resolved = Path(raw).resolve()
    if resolved.suffix not in _VALID_CONFIG_EXTENSIONS:
        raise ValueError(f"Config path must be a .yaml/.yml file, got: {resolved.name}")
    return resolved


def load_config(config_path: Optional[str] = None) -> AppConfig:
    """Load config with two-layer merging: default.yaml then local overrides.

    Layer 1: config/default.yaml (always loaded, sane defaults in VCS)
    Layer 2: config/local.yaml or path from CONCENTRATOR_CONFIG env var
             (user-specific overrides, gitignored)
    """
    cfg = AppConfig()

    _apply_yaml(cfg, Path("config/default.yaml"))

    local = config_path or os.environ.get("CONCENTRATOR_CONFIG", "config/local.yaml")
    _apply_yaml(cfg, _validated_config_path(local))

    return cfg


def _get_local_yaml_path() -> Path:
    """Resolve the local.yaml path used for user overrides."""
    raw = os.environ.get("CONCENTRATOR_CONFIG", "config/local.yaml")
    return _validated_config_path(raw)


def save_section_to_yaml(section: str, values: dict) -> None:
    """Merge values into a section of local.yaml without destroying other sections.

    Reads the existing file (if any), updates only the specified section,
    and writes back. Creates the file if it doesn't exist.
    """
    path = _get_local_yaml_path()
    existing: dict = {}
    if path.exists():
        with open(path, "r") as fh:
            existing = yaml.safe_load(fh) or {}

    if section not in existing:
        existing[section] = {}
    if isinstance(existing[section], dict):
        existing[section].update(values)
    else:
        existing[section] = values

    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(path, "w") as fh:
            yaml.dump(existing, fh, default_flow_style=False, sort_keys=False)
    except PermissionError:
        import getpass
        hint_user = getpass.getuser() or "meshpoint"
        raise PermissionError(
            f"Cannot write to {path}. "
            f"Fix with: sudo chown {hint_user}:{hint_user} {path}"
        )


def validate_activation(config: AppConfig) -> None:
    """Require a valid signed API key before the concentrator pipeline starts."""
    token = config.upstream.auth_token
    if not token:
        print("\n  Mesh Point is not activated.\n")
        print("  An API key is required to run the concentrator.")
        print("  Get a free key at https://meshradar.io\n")
        print("  Then run:  meshpoint setup\n")
        sys.exit(1)

    from src.activation import verify_license_key

    if not verify_license_key(token):
        print("\n  Invalid API key.\n")
        print("  The key in your config is not a valid Mesh Radar license.")
        print("  Generate a new key at https://meshradar.io\n")
        print("  Then run:  meshpoint setup\n")
        sys.exit(1)
