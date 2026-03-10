"""Generates config/local.yaml and a unique device ID for provisioning.

Called by provision.py with device-specific parameters. Writes files
directly to the target SD card rootfs path.
"""

from __future__ import annotations

import uuid
from pathlib import Path

import yaml


def generate_local_config(
    device_name: str,
    api_key: str,
    latitude: float,
    longitude: float,
    wifi_ssid: str = "",
) -> dict:
    """Build a local.yaml config dict for a provisioned device."""
    return {
        "capture": {
            "sources": ["concentrator"],
            "concentrator_spi_device": "/dev/spidev0.0",
        },
        "upstream": {
            "enabled": True,
            "url": "wss://api.meshradar.io",
            "auth_token": api_key,
        },
        "device": {
            "device_name": device_name,
            "latitude": latitude,
            "longitude": longitude,
            "hardware_description": "RAK2287 + Raspberry Pi 4",
        },
    }


def generate_device_id() -> str:
    return str(uuid.uuid4())


def write_config_to_rootfs(
    rootfs_path: Path,
    config: dict,
    device_id: str,
) -> Path:
    """Write local.yaml and .device_id to the SD card rootfs."""
    config_dir = rootfs_path / "opt" / "meshpoint" / "config"
    config_dir.mkdir(parents=True, exist_ok=True)

    local_yaml = config_dir / "local.yaml"
    local_yaml.write_text(yaml.dump(config, default_flow_style=False, sort_keys=False))

    device_id_file = config_dir / ".device_id"
    device_id_file.write_text(device_id)

    return local_yaml


def write_hostname(rootfs_path: Path, hostname: str) -> None:
    """Set the Pi's hostname on the SD card."""
    etc = rootfs_path / "etc"
    (etc / "hostname").write_text(hostname + "\n")

    hosts_file = etc / "hosts"
    if hosts_file.exists():
        lines = hosts_file.read_text().splitlines()
        new_lines = []
        for line in lines:
            if "127.0.1.1" in line:
                new_lines.append(f"127.0.1.1\t{hostname}")
            else:
                new_lines.append(line)
        hosts_file.write_text("\n".join(new_lines) + "\n")


def write_wifi_config(rootfs_path: Path, ssid: str, password: str) -> None:
    """Write a NetworkManager connection file for Bookworm-era Pi OS."""
    nm_dir = rootfs_path / "etc" / "NetworkManager" / "system-connections"
    nm_dir.mkdir(parents=True, exist_ok=True)

    connection = f"""[connection]
id=meshpoint-wifi
type=wifi
autoconnect=true
autoconnect-priority=10

[wifi]
mode=infrastructure
ssid={ssid}

[wifi-security]
key-mgmt=wpa-psk
psk={password}

[ipv4]
method=auto

[ipv6]
method=auto
"""

    conn_file = nm_dir / "meshpoint-wifi.nmconnection"
    conn_file.write_text(connection)


def enable_ssh(boot_path: Path) -> None:
    """Create the empty 'ssh' file on the boot partition to enable SSH."""
    ssh_file = boot_path / "ssh"
    ssh_file.touch()
