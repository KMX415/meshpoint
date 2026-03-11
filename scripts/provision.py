"""
Mesh Point Provisioning Wizard

Interactive tool for pre-configuring SD cards so devices are
plug-and-play. Run this on your computer with the SD card mounted.

Usage:
    python scripts/provision.py

The wizard walks you through:
    1. SD card path
    2. Device name
    3. Wi-Fi credentials
    4. Device location (lat/lng)
    5. API key
    6. Summary + confirmation

All devices are provisioned under your admin account. Friends just
plug in the device and it auto-registers with Mesh Radar.
"""

from __future__ import annotations

import sys
from pathlib import Path

try:
    import yaml  # noqa: F401
except ImportError:
    print("ERROR: PyYAML is required.  Run:  pip install pyyaml")
    sys.exit(1)

from provision_config import (
    enable_ssh,
    generate_device_id,
    generate_local_config,
    write_config_to_rootfs,
    write_hostname,
    write_wifi_config,
)

GREEN = "\033[92m"
CYAN = "\033[96m"
YELLOW = "\033[93m"
RED = "\033[91m"
BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"

_last_api_key: str = ""


def main() -> None:
    _print_banner()

    boot_path, root_path = _step_sd_card()
    device_name = _step_device_name()
    wifi_ssid, wifi_pass = _step_wifi()
    latitude, longitude = _step_location()
    api_key = _step_api_key()

    device_id = generate_device_id()
    hostname = device_name.lower().replace(" ", "-")

    config = generate_local_config(
        device_name=device_name,
        api_key=api_key,
        latitude=latitude,
        longitude=longitude,
        wifi_ssid=wifi_ssid,
    )

    _print_summary(device_name, hostname, wifi_ssid, latitude, longitude, device_id)

    if not _confirm("Write configuration to SD card?"):
        print(f"\n  {YELLOW}Cancelled.{RESET}")
        return

    print()
    _write_all(boot_path, root_path, config, device_id, hostname, wifi_ssid, wifi_pass)
    _print_done(device_name, hostname)

    if _confirm("Provision another device?", default_yes=False):
        print()
        main()


def _print_banner() -> None:
    print()
    print(f"  {CYAN}{BOLD}╔══════════════════════════════════════╗{RESET}")
    print(f"  {CYAN}{BOLD}║   Mesh Point Provisioning Wizard     ║{RESET}")
    print(f"  {CYAN}{BOLD}╚══════════════════════════════════════╝{RESET}")
    print()
    print(f"  {DIM}Pre-configure SD cards for plug-and-play Mesh Points.{RESET}")
    print(f"  {DIM}Devices register with your Mesh Radar fleet automatically.{RESET}")
    print()


def _step_sd_card() -> tuple[Path, Path]:
    print(f"  {BOLD}[1/5] SD Card Location{RESET}")
    print()
    print(f"  {DIM}Insert the SD card (freshly flashed with Raspberry Pi OS).{RESET}")
    print(f"  {DIM}You need paths to both partitions:{RESET}")
    print()
    print(f"  {DIM}  Windows:  boot = D:\\   rootfs = not accessible (skip){RESET}")
    print(f"  {DIM}  Mac:      boot = /Volumes/bootfs   rootfs = /Volumes/rootfs{RESET}")
    print(f"  {DIM}  Linux:    boot = /media/you/bootfs  rootfs = /media/you/rootfs{RESET}")
    print()

    boot_path = Path(_prompt("  Boot partition path: ").strip().strip('"'))
    if not boot_path.exists():
        print(f"  {RED}Path does not exist: {boot_path}{RESET}")
        sys.exit(1)

    root_input = _prompt("  Rootfs partition path (or Enter to skip): ").strip().strip('"')
    if root_input:
        root_path = Path(root_input)
        if not root_path.exists():
            print(f"  {RED}Path does not exist: {root_path}{RESET}")
            sys.exit(1)
    else:
        root_path = boot_path
        print(f"  {DIM}  Using boot path for both partitions.{RESET}")

    print()
    return boot_path, root_path


def _step_device_name() -> str:
    print(f"  {BOLD}[2/5] Device Name{RESET}")
    print()
    print(f"  {DIM}A short, descriptive name for this Mesh Point.{RESET}")
    print(f"  {DIM}Shows up in your fleet view on meshradar.io.{RESET}")
    print()
    print(f"  {DIM}  Examples: meshpoint-nyc, meshpoint-denver, kmax-home{RESET}")
    print()

    name = _prompt("  Device name: ").strip()
    if not name:
        name = "meshpoint"
    print(f"  {GREEN}→ {name}{RESET}")
    print()
    return name


def _step_wifi() -> tuple[str, str]:
    print(f"  {BOLD}[3/5] Wi-Fi Credentials{RESET}")
    print()
    print(f"  {DIM}The Wi-Fi network the device will connect to.{RESET}")
    print(f"  {DIM}Ask your friend for their network name and password.{RESET}")
    print()

    ssid = _prompt("  Wi-Fi network name (SSID): ").strip()
    password = _prompt("  Wi-Fi password: ").strip()

    if ssid:
        print(f"  {GREEN}→ Wi-Fi: {ssid}{RESET}")
    else:
        print(f"  {YELLOW}→ No Wi-Fi configured (Ethernet only){RESET}")
    print()
    return ssid, password


def _step_location() -> tuple[float, float]:
    print(f"  {BOLD}[4/5] Device Location{RESET}")
    print()
    print(f"  {DIM}Where the device will physically be. Used for the map{RESET}")
    print(f"  {DIM}on meshradar.io and the local dashboard.{RESET}")
    print()
    print(f"  {DIM}  Tip: Right-click on Google Maps → copy coordinates{RESET}")
    print(f"  {DIM}  Format: 40.7128, -74.0060{RESET}")
    print()

    coords = _prompt("  Latitude, Longitude (comma-separated): ").strip()
    parts = coords.replace(" ", "").split(",")
    if len(parts) != 2:
        print(f"  {RED}Expected two values separated by a comma.{RESET}")
        sys.exit(1)

    try:
        lat = float(parts[0])
        lng = float(parts[1])
    except ValueError:
        print(f"  {RED}Could not parse coordinates. Use format: 40.7128, -74.0060{RESET}")
        sys.exit(1)

    print(f"  {GREEN}→ Location: {lat}, {lng}{RESET}")
    print()
    return lat, lng


def _step_api_key() -> str:
    global _last_api_key

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from src.activation import verify_license_key

    print(f"  {BOLD}[5/5] Mesh Radar API Key{RESET}")
    print()
    print(f"  {DIM}Your API key from meshradar.io > Account > API Keys.{RESET}")
    print(f"  {DIM}All provisioned devices use the same key (your account).{RESET}")

    if _last_api_key:
        print()
        print(f"  {DIM}  Last used: {_last_api_key[:12]}...{RESET}")
        if _confirm("  Use the same key?", default_yes=True):
            print(f"  {GREEN}→ Using previous key{RESET}")
            print()
            return _last_api_key

    print()
    while True:
        key = _prompt("  API key: ").strip()
        if not key:
            print(f"  {RED}An API key is required. Get one at meshradar.io{RESET}")
            print()
            continue
        if verify_license_key(key):
            break
        print(f"  {RED}That key is not valid. Please check and try again.{RESET}")
        print()

    _last_api_key = key
    print(f"  {GREEN}→ Key verified: {key[:12]}...{RESET}")
    print()
    return key


def _print_summary(
    name: str,
    hostname: str,
    wifi: str,
    lat: float,
    lng: float,
    device_id: str,
) -> None:
    print()
    print(f"  {BOLD}╔══════════════════════════════════════╗{RESET}")
    print(f"  {BOLD}║  Provisioning Summary                ║{RESET}")
    print(f"  {BOLD}╠══════════════════════════════════════╣{RESET}")
    print(f"  {BOLD}║{RESET}  Device:    {CYAN}{name:<25}{RESET}{BOLD}║{RESET}")
    print(f"  {BOLD}║{RESET}  Hostname:  {hostname:<25}{BOLD}║{RESET}")
    print(f"  {BOLD}║{RESET}  Wi-Fi:     {wifi or '(none -- Ethernet)':<25}{BOLD}║{RESET}")
    print(f"  {BOLD}║{RESET}  Location:  {f'{lat}, {lng}':<25}{BOLD}║{RESET}")
    print(f"  {BOLD}║{RESET}  ID:        {device_id[:8]}...{' ' * 14}{BOLD}║{RESET}")
    print(f"  {BOLD}╚══════════════════════════════════════╝{RESET}")


def _write_all(
    boot_path: Path,
    root_path: Path,
    config: dict,
    device_id: str,
    hostname: str,
    wifi_ssid: str,
    wifi_pass: str,
) -> None:
    print(f"  {DIM}Writing configuration...{RESET}")

    enable_ssh(boot_path)
    print(f"  {GREEN}✓{RESET} SSH enabled")

    config_path = write_config_to_rootfs(root_path, config, device_id)
    print(f"  {GREEN}✓{RESET} Config written to {config_path}")

    try:
        write_hostname(root_path, hostname)
        print(f"  {GREEN}✓{RESET} Hostname set to {hostname}")
    except (PermissionError, FileNotFoundError):
        print(f"  {YELLOW}⚠{RESET} Could not set hostname (rootfs may not be accessible)")

    if wifi_ssid:
        try:
            write_wifi_config(root_path, wifi_ssid, wifi_pass)
            print(f"  {GREEN}✓{RESET} Wi-Fi configured for {wifi_ssid}")
        except (PermissionError, FileNotFoundError):
            print(f"  {YELLOW}⚠{RESET} Could not write Wi-Fi config (rootfs may not be accessible)")


def _print_done(device_name: str, hostname: str) -> None:
    print()
    print(f"  {GREEN}{BOLD}Done!{RESET} SD card is ready.")
    print()
    print(f"  {BOLD}┌──────────────────────────────────────┐{RESET}")
    print(f"  {BOLD}│{RESET}  {CYAN}Text this to your friend:{RESET}           {BOLD}│{RESET}")
    print(f"  {BOLD}│{RESET}                                      {BOLD}│{RESET}")
    print(f"  {BOLD}│{RESET}  Your Mesh Point is ready!           {BOLD}│{RESET}")
    print(f"  {BOLD}│{RESET}  1. Connect the antenna              {BOLD}│{RESET}")
    print(f"  {BOLD}│{RESET}  2. Plug in power                    {BOLD}│{RESET}")
    print(f"  {BOLD}│{RESET}  3. Wait 2 minutes                   {BOLD}│{RESET}")
    print(f"  {BOLD}│{RESET}  4. Dashboard: http://{hostname}:8080{RESET}")
    print(f"  {BOLD}│{RESET}                                      {BOLD}│{RESET}")
    print(f"  {BOLD}│{RESET}  {DIM}That's it -- it's automatic!{RESET}        {BOLD}│{RESET}")
    print(f"  {BOLD}└──────────────────────────────────────┘{RESET}")
    print()


def _prompt(message: str) -> str:
    try:
        return input(message)
    except (EOFError, KeyboardInterrupt):
        print(f"\n  {YELLOW}Cancelled.{RESET}")
        sys.exit(0)


def _confirm(message: str, default_yes: bool = True) -> bool:
    suffix = "[Y/n]" if default_yes else "[y/N]"
    response = _prompt(f"{message} {suffix} ").strip().lower()
    if not response:
        return default_yes
    return response in ("y", "yes")


if __name__ == "__main__":
    main()
