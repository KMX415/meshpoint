"""Interactive setup wizard for first-time Mesh Point provisioning.

Walks the user through hardware detection, API key entry, device
naming, GPS configuration, and generates config/local.yaml.
"""

from __future__ import annotations

import os
import socket
import uuid
from pathlib import Path
from typing import Optional

import yaml

from src.cli.hardware_detect import (
    HardwareReport,
    detect_all,
    print_report,
)

LOCAL_CONFIG_PATH = Path("config/local.yaml")
CLOUD_URL = "https://meshradar.io"


def run_setup() -> None:
    """Main entry point for the interactive setup wizard."""
    _print_banner()

    if LOCAL_CONFIG_PATH.exists():
        if not _confirm("Existing config/local.yaml found. Overwrite?"):
            print("  Setup cancelled.")
            return

    config: dict = {}

    report = _step_hardware_detect()
    _step_capture_source(config, report)
    _step_api_key(config)
    _step_device_name(config)
    _step_location(config, report)
    _step_relay(config, report)
    _step_device_id(config)

    _write_config(config)
    _step_start_service()


def _print_banner() -> None:
    print()
    print("  ╔══════════════════════════════════════╗")
    print("  ║     Mesh Radar -- Mesh Point Setup   ║")
    print("  ╚══════════════════════════════════════╝")
    print()


def _step_hardware_detect() -> HardwareReport:
    """Probe for all available hardware."""
    print("  [1/7] Detecting hardware...")
    report = detect_all()
    print_report(report)
    return report


def _step_capture_source(config: dict, report: HardwareReport) -> None:
    """Choose the LoRa capture source based on detected hardware."""
    print("  [2/7] Capture source")

    if report.concentrator_available:
        print(f"        Concentrator detected on {report.spi_devices[0]}")
        print(f"        Hardware: {report.hardware_description}")
        source = "concentrator"
        spi_device = report.spi_devices[0]
        config["capture"] = {
            "sources": [source],
            "concentrator_spi_device": spi_device,
        }
        config.setdefault("device", {})["hardware_description"] = (
            report.hardware_description
        )
    elif report.serial_ports:
        port = _choose_from_list(
            "Select capture serial port:", report.serial_ports
        )
        config["capture"] = {
            "sources": ["serial"],
            "serial_port": port,
        }
    else:
        print("        No LoRa hardware detected.")
        print("        Connect a RAK2287 concentrator or Meshtastic serial radio")
        print("        and re-run 'meshpoint setup'.")
        config["capture"] = {"sources": []}

    _maybe_add_meshcore_usb(config, report)


def _step_api_key(config: dict) -> None:
    """Prompt for the Mesh Radar API key (required, signature-verified)."""
    from src.activation import verify_license_key

    print("  [3/7] API key")
    print()
    print("        An API key is required to activate this Mesh Point.")
    print(f"        Get a free key at {CLOUD_URL}")
    print()
    print("        Steps:")
    print("          1. Go to meshradar.io and create an account")
    print("          2. Click 'API Keys' in the top bar")
    print("          3. Generate a new key and copy it")
    print()

    while True:
        api_key = _prompt("Paste your API key:").strip()
        if not api_key:
            print("        An API key is required. Get one free at meshradar.io")
            print()
            continue
        if verify_license_key(api_key):
            break
        print("        That key is not valid. Please check and try again.")
        print()

    config["upstream"] = {
        "enabled": True,
        "auth_token": api_key,
    }
    print("        API key verified and saved.")
    print()


def _step_device_name(config: dict) -> None:
    """Choose a name for this Mesh Point."""
    print("  [4/7] Device name")
    default_name = _default_device_name()
    name = _prompt(f"Device name [{default_name}]:").strip()
    if not name:
        name = default_name

    config.setdefault("device", {})["device_name"] = name
    print(f"        Named: {name}")
    print()


def _step_location(config: dict, report: HardwareReport) -> None:
    """Set device GPS coordinates."""
    print("  [5/7] Location")

    gps = report.gps
    if gps.got_fix:
        print(f"        GPS fix acquired: {gps.latitude}, {gps.longitude}")
        print(f"        Altitude: {gps.altitude}m | Satellites: {gps.satellites}")
        if _confirm("Use this GPS position?", default_yes=True):
            config.setdefault("device", {}).update({
                "latitude": gps.latitude,
                "longitude": gps.longitude,
                "altitude": gps.altitude,
            })
            print()
            return

    print("        Enter coordinates manually (used for map placement).")
    print("        Tip: in Google Maps, right-click any location and click")
    print("        the coordinates at the top of the menu to copy them.")
    print("        They copy in decimal format (e.g. 43.8891, -72.2219).")
    print()

    lat = _prompt_float("Latitude (e.g. 42.3601):")
    lon = _prompt_float("Longitude (e.g. -71.0589):")
    alt = _prompt_float("Altitude in meters (or Enter to skip):", required=False)

    device = config.setdefault("device", {})
    if lat is not None:
        device["latitude"] = lat
    if lon is not None:
        device["longitude"] = lon
    if alt is not None:
        device["altitude"] = alt

    print()


def _step_relay(config: dict, report: HardwareReport) -> None:
    """Configure the optional SX1262 relay radio."""
    print("  [6/7] Relay radio (optional)")

    capture_port = config.get("capture", {}).get("serial_port")
    available_ports = [
        p for p in report.serial_ports if p != capture_port
    ]

    if not available_ports:
        print("        No additional serial ports detected for relay.")
        print("        Relay can be configured later in config/local.yaml")
        print()
        return

    print("        A relay radio (SX1262) rebroadcasts packets to extend")
    print("        mesh coverage. It uses a separate serial port.")
    print()

    if _confirm("Configure a relay radio?"):
        port = _choose_from_list(
            "Select relay serial port:", available_ports
        )
        config["relay"] = {
            "enabled": True,
            "serial_port": port,
        }
        print(f"        Relay configured on {port}")
    else:
        print("        Relay skipped.")

    print()


def _step_device_id(config: dict) -> None:
    """Generate a stable, persistent device ID."""
    device_id = str(uuid.uuid4())
    config.setdefault("device", {})["device_id"] = device_id
    print(f"  [7/7] Device ID: {device_id}")
    print()


def _write_config(config: dict) -> None:
    """Write the generated config to config/local.yaml."""
    LOCAL_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)

    with open(LOCAL_CONFIG_PATH, "w") as fh:
        yaml.dump(config, fh, default_flow_style=False, sort_keys=False)

    print(f"  Config written to {LOCAL_CONFIG_PATH}")
    print()


def _step_start_service() -> None:
    """Offer to start the meshpoint systemd service."""
    if not _is_systemd():
        print("  systemd not detected. Start manually with:")
        print("    python -m uvicorn src.api.server:create_app --factory --host 0.0.0.0 --port 8080")
        print()
        return

    if _confirm("Start the Mesh Point service now?", default_yes=True):
        import subprocess

        subprocess.run(
            ["sudo", "systemctl", "start", "meshpoint"],
            check=False,
        )

        import time
        print("  Starting...")
        time.sleep(3)

        result = subprocess.run(
            ["systemctl", "is-active", "meshpoint"],
            capture_output=True, text=True,
        )
        if result.stdout.strip() == "active":
            print("  Mesh Point is running!")
            print()
            print("  View the local dashboard at: http://localhost:8080")
            print("  Check status anytime with:   meshpoint status")
            print("  View logs with:               meshpoint logs")
        else:
            print("  Service may still be starting. Check with: meshpoint status")
    else:
        print("  Start later with: sudo systemctl start meshpoint")

    print()
    print("  Setup complete!")
    print()


def _maybe_add_meshcore_usb(config: dict, report: HardwareReport) -> None:
    """Offer to enable MeshCore USB monitoring if USB serial ports exist."""
    capture_port = config.get("capture", {}).get("serial_port")
    candidates = [
        p for p in report.meshcore_usb_candidates if p != capture_port
    ]

    if not candidates:
        return

    print()
    print("        USB serial port(s) detected that could be a MeshCore node:")
    for port in candidates:
        print(f"          - {port}")
    print()
    print("        If you have a MeshCore device (Heltec, T-Beam, etc.) plugged")
    print("        in via USB, Mesh Point can monitor its traffic automatically.")
    print()

    if not _confirm("Enable MeshCore USB monitoring?"):
        config.setdefault("capture", {}).setdefault(
            "meshcore_usb", {}
        )["auto_detect"] = False
        print("        MeshCore USB disabled.")
        print()
        return

    sources = config.setdefault("capture", {}).setdefault("sources", [])
    if "meshcore_usb" not in sources:
        sources.append("meshcore_usb")

    if len(candidates) == 1:
        chosen_port = candidates[0]
    else:
        chosen_port = _choose_from_list(
            "Select MeshCore USB port:", candidates
        )

    config["capture"].setdefault("meshcore_usb", {})["serial_port"] = (
        chosen_port
    )
    print(f"        MeshCore USB enabled on {chosen_port}")
    print()


# ── Helpers ─────────────────────────────────────────────────────────

def _prompt(message: str) -> str:
    """Print an indented prompt and read input."""
    return input(f"        {message} ")


def _confirm(message: str, default_yes: bool = False) -> bool:
    """Yes/no prompt with a default."""
    suffix = "[Y/n]" if default_yes else "[y/N]"
    answer = _prompt(f"{message} {suffix}").strip().lower()
    if not answer:
        return default_yes
    return answer in ("y", "yes")


def _prompt_float(
    message: str, required: bool = True
) -> Optional[float]:
    """Prompt for a float value."""
    while True:
        raw = _prompt(message).strip()
        if not raw:
            if required:
                print("          A value is required.")
                continue
            return None
        try:
            return round(float(raw), 6)
        except ValueError:
            print("          Please enter a valid number.")


def _choose_from_list(message: str, options: list[str]) -> str:
    """Present numbered options and return the chosen value."""
    print(f"        {message}")
    for i, option in enumerate(options, 1):
        print(f"          {i}. {option}")

    while True:
        raw = _prompt(f"Choice [1-{len(options)}]:").strip()
        try:
            idx = int(raw) - 1
            if 0 <= idx < len(options):
                return options[idx]
        except ValueError:
            pass
        print(f"          Please enter a number between 1 and {len(options)}.")


def _default_device_name() -> str:
    """Generate a sensible default device name from the hostname."""
    hostname = socket.gethostname().split(".")[0]
    return f"Mesh Point {hostname.capitalize()}"


def _is_systemd() -> bool:
    """Check if we're running on a systemd-based system."""
    return os.path.isdir("/run/systemd/system")
