"""Colored terminal logging for Mesh Point.

Provides a rich log formatter with ANSI colors, an ASCII art startup
banner, and a compact packet display with RSSI signal bars.
"""

from __future__ import annotations

import logging
import os
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.config import AppConfig
    from src.models.packet import Packet

_USE_COLOR = (
    os.environ.get("FORCE_COLOR", "") == "1"
    or (hasattr(sys.stdout, "isatty") and sys.stdout.isatty())
)

# ── ANSI escape codes ────────────────────────────────────────────────

RESET = "\033[0m" if _USE_COLOR else ""
BOLD = "\033[1m" if _USE_COLOR else ""
DIM = "\033[2m" if _USE_COLOR else ""

RED = "\033[31m" if _USE_COLOR else ""
GREEN = "\033[32m" if _USE_COLOR else ""
YELLOW = "\033[33m" if _USE_COLOR else ""
BLUE = "\033[34m" if _USE_COLOR else ""
MAGENTA = "\033[35m" if _USE_COLOR else ""
CYAN = "\033[36m" if _USE_COLOR else ""
WHITE = "\033[37m" if _USE_COLOR else ""

BRIGHT_GREEN = "\033[92m" if _USE_COLOR else ""
BRIGHT_RED = "\033[91m" if _USE_COLOR else ""
BRIGHT_YELLOW = "\033[93m" if _USE_COLOR else ""
BRIGHT_CYAN = "\033[96m" if _USE_COLOR else ""

_LEVEL_COLORS = {
    "DEBUG": DIM,
    "INFO": GREEN,
    "WARNING": YELLOW,
    "ERROR": BRIGHT_RED,
    "CRITICAL": BOLD + BRIGHT_RED,
}

_BAR_FULL = "▓"
_BAR_EMPTY = "░"
_BAR_SEGMENTS = 10


# ── Colored log formatter ────────────────────────────────────────────

class ColoredFormatter(logging.Formatter):
    """Log formatter that adds ANSI colors and compact timestamps."""

    def format(self, record: logging.LogRecord) -> str:
        ts = self.formatTime(record, "%H:%M:%S")
        level = record.levelname
        color = _LEVEL_COLORS.get(level, "")
        name = record.name.rsplit(".", 1)[-1]

        msg = record.getMessage()
        if record.exc_info and not record.exc_text:
            record.exc_text = self.formatException(record.exc_info)
        if record.exc_text:
            msg = f"{msg}\n{record.exc_text}"

        return (
            f"{DIM}{ts}{RESET} "
            f"{color}{level:<7}{RESET} "
            f"{CYAN}{name}{RESET}: "
            f"{msg}"
        )


def setup_logging(level: int = logging.INFO) -> None:
    """Install the colored formatter on the root logger."""
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(ColoredFormatter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)


# ── RSSI signal bar ─────────────────────────────────────────────────

def _rssi_bar(rssi: float) -> str:
    """Render a 10-segment signal-strength bar, color-graded by RSSI."""
    clamped = max(-120.0, min(-50.0, rssi))
    filled = round(((clamped + 120.0) / 70.0) * _BAR_SEGMENTS)
    filled = max(0, min(_BAR_SEGMENTS, filled))

    if rssi > -80:
        color = GREEN
    elif rssi > -100:
        color = YELLOW
    else:
        color = RED

    bar = _BAR_FULL * filled + _BAR_EMPTY * (_BAR_SEGMENTS - filled)
    return f"{color}{bar}{RESET}"


# ── Packet display ──────────────────────────────────────────────────

def _payload_summary(packet: Packet) -> str:
    """Extract a short inline summary from the decoded payload."""
    payload = packet.decoded_payload
    if not payload:
        return ""

    ptype = packet.packet_type.value
    parts: list[str] = []

    if ptype == "text":
        text = payload.get("text", "")
        if text:
            parts.append(f'"{text[:60]}"')
    elif ptype == "position":
        lat = payload.get("latitude") or payload.get("lat")
        lon = payload.get("longitude") or payload.get("lon")
        if lat is not None and lon is not None:
            parts.append(f"lat={lat:.4f} lon={lon:.4f}")
        alt = payload.get("altitude") or payload.get("alt")
        if alt is not None:
            parts.append(f"alt={alt:.0f}m")
    elif ptype == "telemetry":
        batt = payload.get("battery_level") or payload.get("voltage")
        if batt is not None:
            parts.append(f"batt={batt}")
        temp = payload.get("temperature")
        if temp is not None:
            parts.append(f"temp={temp}C")
    elif ptype == "nodeinfo":
        name = payload.get("long_name") or payload.get("short_name")
        if name:
            parts.append(f'"{name}"')
        role = payload.get("role")
        if role:
            parts.append(f"role={role}")
    elif ptype == "waypoint":
        name = payload.get("name")
        if name:
            parts.append(f'"{name}"')
        lat = payload.get("latitude")
        lon = payload.get("longitude")
        if lat is not None and lon is not None:
            parts.append(f"lat={lat:.4f} lon={lon:.4f}")
    elif ptype == "range_test":
        text = payload.get("text", "")
        if text:
            parts.append(f"seq={text}")
    elif ptype == "store_forward":
        rr = payload.get("rr")
        if rr is not None:
            parts.append(f"rr={rr}")
        total = payload.get("messages_total")
        if total is not None:
            parts.append(f"msgs={total}")
    elif ptype == "detection_sensor":
        text = payload.get("text", "")
        if text:
            parts.append(text[:60])
    elif ptype == "paxcounter":
        wifi = payload.get("wifi")
        ble = payload.get("ble")
        if wifi is not None:
            parts.append(f"wifi={wifi}")
        if ble is not None:
            parts.append(f"ble={ble}")
    elif ptype == "map_report":
        name = payload.get("long_name") or payload.get("short_name")
        if name:
            parts.append(f'"{name}"')
        fw = payload.get("firmware_version")
        if fw:
            parts.append(f"fw={fw}")
    elif ptype == "encrypted":
        size = payload.get("payload_size")
        if size is not None:
            parts.append(f"{size} bytes")
        ch = payload.get("channel_hash")
        if ch is not None:
            parts.append(f"ch=0x{ch:02x}")

    return " ".join(parts)


def print_packet(packet: Packet) -> None:
    """Print a rich single-line packet event to stdout."""
    proto = packet.protocol.value
    proto_color = BLUE if proto == "meshtastic" else MAGENTA

    rssi = packet.signal.rssi if packet.signal else 0.0
    snr = packet.signal.snr if packet.signal else 0.0
    bar = _rssi_bar(rssi)

    ptype = packet.packet_type.value.upper()
    summary = _payload_summary(packet)
    summary_str = f"  {DIM}{summary}{RESET}" if summary else ""

    line = (
        f" {BRIGHT_GREEN}>>{RESET} "
        f"{BOLD}PKT{RESET}  "
        f"{proto_color}{proto:<11}{RESET} "
        f"{WHITE}{packet.source_id}{RESET} -> "
        f"{WHITE}{packet.destination_id}{RESET}  "
        f"{YELLOW}{ptype:<12}{RESET} "
        f"{DIM}rssi{RESET} {rssi:>6.1f} {bar} "
        f"{DIM}snr{RESET} {snr:>5.1f}"
        f"{summary_str}"
    )
    print(line, flush=True)


# ── Startup banner ──────────────────────────────────────────────────

def _local_ip() -> str:
    """Get the primary LAN IP via hostname -I (Linux)."""
    try:
        import subprocess
        result = subprocess.run(
            ["hostname", "-I"], capture_output=True, text=True, timeout=2,
        )
        ips = result.stdout.strip().split()
        if ips:
            return ips[0]
    except Exception:
        pass
    return "127.0.0.1"


_BANNER_ART = r"""
  {c}┌──────────────────────────────────────────────┐{r}
  {c}│{r}  {g}╔╦╗╔═╗╔═╗╦ ╦  ╔═╗╔═╗╦╔╗╔╔╦╗{r}              {c}│{r}
  {c}│{r}  {g}║║║║╣ ╚═╗╠═╣  ╠═╝║ ║║║║║ ║{r}               {c}│{r}
  {c}│{r}  {g}╩ ╩╚═╝╚═╝╩ ╩  ╩  ╚═╝╩╝╚╝ ╩{r}               {c}│{r}
  {c}└──────────────────────────────────────────────┘{r}"""


_SOURCE_DESCRIPTIONS = {
    "concentrator": "concentrator (SX1302 8-ch)",
    "serial": "serial radio",
    "meshcore_usb": "MeshCore USB node",
    "mock": "mock source",
}


def _describe_sources(config: AppConfig) -> str:
    """Build a human-readable source list for the startup banner."""
    parts = [
        _SOURCE_DESCRIPTIONS.get(s, s) for s in config.capture.sources
    ]
    if (
        "meshcore_usb" not in config.capture.sources
        and config.capture.meshcore_usb.auto_detect
    ):
        parts.append("MeshCore USB (auto-detect)")
    return ", ".join(parts) or "none"


def _region_frequency_line(config: AppConfig) -> str:
    """Resolve the actual primary frequency from the radio config."""
    radio = config.radio
    try:
        from src.hal.concentrator_config import ConcentratorChannelPlan
        plan = ConcentratorChannelPlan.from_radio_config(
            region=radio.region,
            frequency_mhz=radio.frequency_mhz,
            spreading_factor=radio.spreading_factor,
            bandwidth_khz=radio.bandwidth_khz,
        )
        if plan.single_sf_channel:
            freq = plan.single_sf_channel.frequency_hz / 1_000_000
            sf = plan.single_sf_channel.spreading_factor
            bw = plan.single_sf_channel.bandwidth_khz
            region_tag = f" ({radio.region})" if radio.region else ""
            return f"{freq:.3f} MHz / SF{sf} / BW{bw:.0f}{region_tag}"
    except Exception:
        pass
    return f"{radio.frequency_mhz} MHz / SF{radio.spreading_factor} / BW{radio.bandwidth_khz:.0f}"


def print_banner(config: AppConfig) -> None:
    """Print the ASCII art startup banner with live config values."""
    from src.version import __version__

    art = _BANNER_ART.format(c=CYAN, g=BRIGHT_GREEN, r=RESET)
    print(art)

    device = config.device
    upstream = config.upstream
    dashboard = config.dashboard
    source_desc = _describe_sources(config)

    info_lines = [
        ("Device", f"{device.device_name} ({device.device_id or 'unset'})"),
        ("Version", __version__),
        ("Source", source_desc),
        ("Frequency", _region_frequency_line(config)),
    ]
    if upstream.enabled:
        info_lines.append(("Upstream", upstream.url))
    else:
        info_lines.append(("Upstream", f"{DIM}disabled{RESET}"))
    info_lines.append(("Dashboard", f"http://{_local_ip()}:{dashboard.port}"))

    for label, value in info_lines:
        print(f"   {DIM}{label:<12}{RESET} {value}")

    print(f"  {CYAN}{'─' * 46}{RESET}")
    print()
