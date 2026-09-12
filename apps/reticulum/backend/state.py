"""Reticulum settings with region-aware defaults and preserved explicit values."""

from __future__ import annotations

import re
from typing import Any
from . import regional

_DEFAULTS: dict[str, Any] = {
    "display_name": "Meshpoint",
    "reticulum_config_dir": "data/reticulum/rns_config",
    "identity_path": "data/reticulum/identity",
    "lxmf_storage_dir": "data/reticulum/lxmf",
    # Optional: an ntfy topic / webhook URL. When set, an inbound LXMF direct
    # message fires a one-line POST there (fire-and-forget). Blank = off.
    "notify_url": "",
    # LXMF propagation node: run a store-and-forward relay so peers who were
    # offline can sync their messages from this box later. Off by default.
    # storage_limit_mb caps the on-disk propagation store (0 = LXMF default).
    "propagation_enabled": False,
    "propagation_storage_limit_mb": 250,
    # Client side of propagation: an lxmf.propagation destination hash to
    # route outbound-to-offline messages through and sync a parked inbox
    # from. Blank = don't use one. auto_sync_interval_s: 0 = manual only,
    # else re-sync every N seconds (floored at 300 by the validator).
    "propagation_outbound_node": "",
    "propagation_auto_sync_interval_s": 0,
    # Telemetry publish: periodically send this box's own host stats (CPU
    # temp, load, RAM/disk) as an LXMF telemetry frame to a collector
    # address, Sideband-style. Off by default. interval floored at 300.
    "telemetry_enabled": False,
    "telemetry_collector": "",
    "telemetry_interval_s": 900,
    # Include the operator's fixed location (Configuration -> GPS pin,
    # core's device.latitude/longitude) in the telemetry frame. Opt-in --
    # off means the collector never learns where this node is.
    "telemetry_include_location": False,
    # RF and backbone are independent interfaces rnsd can run at once or
    # separately -- at least one must stay on (enforced by config_routes.py's
    # ReticulumUpdate validator), same as NomadNet needs one of them to
    # actually reach anyone.
    "rnode_enabled": False,
    "rnode_serial_port": "",
    "rnode_frequency_hz": None,
    "rnode_bandwidth_hz": 125_000,
    "rnode_tx_power": 7,
    "rnode_spreading_factor": 7,
    "rnode_coding_rate": 5,
    "rnode_airtime_limit_short": None,
    "rnode_airtime_limit_long": None,
    "backbone_enabled": False,
    "backbone_host": "",
    "backbone_port": 4242,
    # Operator-added extra RNS interfaces (Settings tab). A list of
    # {name, type, enabled, ...type-specific fields}. Consumed only by
    # write_rnsd_config.py -- rnsd needs a restart to apply.
    "extra_interfaces": [],
    # NomadNet "Browse" tab: path/link timeout budget in seconds (request
    # gets 1.5x). 20 suits a TCP backbone; bump for multi-hop LoRa nodes.
    "nomad_timeout_s": 20,
    # Host a NomadNet node (serve pages) -- opt-in, off by default. Same
    # RNS identity as LXMF, so you appear as both "message me" and
    # "browse me" on one hash. Applies on restart.
    "node_enabled": False,
    "node_name": "",                       # blank = use display_name
    "node_pages_dir": "data/reticulum/pages",
    "node_announce_interval_s": 21600,     # 6h
    # Optional: a hackerspace SpaceAPI URL. When set, the node also serves
    # /page/spacestate.mu (is-the-space-open + address/contacts, fetched +
    # cached). Blank = that page isn't registered.
    "node_spaceapi_url": "",
    # Optional: an iCalendar (.ics) feed URL. When set, the node also serves
    # /page/events.mu (upcoming events, fetched + cached, same lazy refresh as
    # spacestate). Blank = that page isn't registered.
    "node_events_ical_url": "",
    # Optional: auto-reply to inbound LXMF DMs matching a known command
    # (help/ping/stats/spacestate/events/nodes) with the same data the
    # hosted node's own .mu pages show. Requires node_enabled -- enforced by
    # config_routes.py's validator, since every command answers from data
    # only a hosted node caches.
    "talkback_enabled": False,
}

_config: dict[str, Any] = dict(_DEFAULTS)
_region = "UNKNOWN"


def init(config: dict, region: str = "UNKNOWN") -> None:
    """Seed from ``reg.config`` (a copy of ``plugins.reticulum``). A missing
    or blank key falls back to core's original default -- a user-edited
    YAML typo must not crash the plugin."""
    global _config, _region
    _region = str(region or "UNKNOWN").upper()
    merged = {**_DEFAULTS, **regional.defaults(_region)}
    for key in _DEFAULTS:
        value = config.get(key)
        if value is not None and value != "":
            merged[key] = value
    # rnode_serial_port is legitimately "" (not configured) -- take it verbatim.
    if "rnode_serial_port" in config:
        merged["rnode_serial_port"] = config.get("rnode_serial_port") or ""
    _config = merged


def display_name() -> str:
    return str(_config["display_name"])


def reticulum_config_dir() -> str:
    return str(_config["reticulum_config_dir"])


def identity_path() -> str:
    return str(_config["identity_path"])


def lxmf_storage_dir() -> str:
    return str(_config["lxmf_storage_dir"])


def extra_interfaces() -> list[dict]:
    """Operator-added RNS interfaces, resolved -- a list of dicts. Only
    read by the Settings tab; write_rnsd_config.py reads the raw YAML."""
    val = _config.get("extra_interfaces")
    return [dict(e) for e in val if isinstance(e, dict)] if isinstance(val, list) else []


def contacts_path() -> str:
    """The operator's petname address book -- a JSON file next to the
    identity / LXMF store, so it follows a relocated reticulum data dir
    rather than a hardcoded ``data/reticulum/``."""
    from pathlib import Path

    return str(Path(_config["identity_path"]).parent / "contacts.json")


def notify_url() -> str:
    return str(_config.get("notify_url") or "").strip()


def propagation_config() -> dict[str, Any]:
    """LXMF propagation settings, resolved -- both the local relay
    (``enabled``/``storage_limit_mb``) and the client side
    (``outbound_node``/``auto_sync_interval_s``)."""
    return {
        "enabled": bool(_config.get("propagation_enabled")),
        "storage_limit_mb": max(0, int(_config.get("propagation_storage_limit_mb") or 0)),
        "outbound_node": str(_config.get("propagation_outbound_node") or "").strip().lower().replace(":", "").strip("<>"),
        "auto_sync_interval_s": max(0, int(_config.get("propagation_auto_sync_interval_s") or 0)),
    }


def _parse_collectors(raw: str) -> list[str]:
    """``telemetry_collector`` is a textarea -- one hash per line (commas /
    extra whitespace tolerated). Normalise, drop blanks + dupes."""
    seen: set = set()
    out: list[str] = []
    for token in re.split(r"[\s,]+", str(raw or "")):
        h = token.strip().lower().replace(":", "").strip("<>")
        if h and h not in seen:
            seen.add(h)
            out.append(h)
    return out


def telemetry_config() -> dict[str, Any]:
    """Telemetry-publish settings, resolved. ``collectors`` is the parsed
    list; ``collector`` is the first (back-compat / simple display)."""
    collectors = _parse_collectors(_config.get("telemetry_collector") or "")
    return {
        "enabled": bool(_config.get("telemetry_enabled")),
        "collectors": collectors,
        "collector": collectors[0] if collectors else "",
        "interval_s": max(300, int(_config.get("telemetry_interval_s") or 900)),
        "include_location": bool(_config.get("telemetry_include_location")),
    }


def node_config() -> dict[str, Any]:
    """The NomadNet-node hosting settings, resolved (name falls back to
    display_name)."""
    return {
        "enabled": bool(_config["node_enabled"]),
        "name": str(_config["node_name"]).strip() or display_name(),
        "pages_dir": str(_config["node_pages_dir"]),
        "announce_interval_s": int(_config["node_announce_interval_s"] or 21600),
        "spaceapi_url": str(_config.get("node_spaceapi_url") or "").strip(),
        "events_ical_url": str(_config.get("node_events_ical_url") or "").strip(),
        "talkback_enabled": bool(_config.get("talkback_enabled")),
    }


def to_dict() -> dict[str, Any]:
    return {**_config, **regional.describe(_region)}


# --- settings-tab writes ----------------------------------------------------

_ALLOWED_UPDATE_KEYS = frozenset(_DEFAULTS)  # never "enabled" -- that's the
# Settings -> Plugins toggle, same as every other plugin.


def set_config(updates: dict) -> None:
    """Merge settings-tab values (already validated by config_routes.py's
    pydantic model) into state and persist to ``plugins.reticulum``. A
    ``DapnetSerialSource``-style live effect isn't possible here -- the
    LxmfService reads these once at construction -- so, like every other
    plugin's config change, this takes effect on the next restart (and,
    for the RNode/backbone fields, an rnsd restart too)."""
    global _config
    merged = dict(_config)
    for key, value in updates.items():
        if key in _ALLOWED_UPDATE_KEYS:
            if value is None and key in ("rnode_airtime_limit_short", "rnode_airtime_limit_long"):
                value = regional.defaults(_region).get(key)
            merged[key] = value
    previous = _config
    _config = merged
    try:
        _persist()
    except Exception:
        _config = previous
        raise


def _current_saved_config() -> dict:
    """Read ``plugins.reticulum``'s CURRENT on-disk shape (not this
    module's load-time snapshot) so a settings save never clobbers a
    same-session Settings -> Plugins enable/disable toggle -- same
    reasoning as the DAPNET plugin's own state._current_saved_config()."""
    import yaml

    from src.config import _get_local_yaml_path  # noqa: SLF001 -- see docstring

    path = _get_local_yaml_path()
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    section = data.get("plugins")
    if not isinstance(section, dict):
        return {}
    current = section.get("reticulum")
    return dict(current) if isinstance(current, dict) else {}


def _persist() -> None:
    from src.config import save_section_to_yaml

    current = _current_saved_config()
    current.update(_config)
    save_section_to_yaml("plugins", {"reticulum": current})
