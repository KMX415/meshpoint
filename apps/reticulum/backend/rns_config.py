"""Reticulum daemon configuration adapted from the contributor generator."""
_TEMPLATE = """\
# Generated from Meshpoint Reticulum settings.
# Replaced when the managed worker restarts.

[reticulum]
  enable_transport = False
  share_instance = Yes
  instance_name = meshpoint

[logging]
  loglevel = 4

[interfaces]

  [[Default Interface]]
    type = AutoInterface
    enabled = No
{rnode_block}{backbone_block}{extra_block}"""

_RNODE_TEMPLATE = """
  [[RNode LoRa]]
    type = RNodeInterface
    enabled = Yes
    port = {rnode_serial_port}

    frequency = {rnode_frequency_hz}
    bandwidth = {rnode_bandwidth_hz}
    txpower = {rnode_tx_power}
    spreadingfactor = {rnode_spreading_factor}
    codingrate = {rnode_coding_rate}
{airtime_block}"""

_BACKBONE_TEMPLATE = """
  [[ReticulumNet Internet]]
    type = TCPClientInterface
    enabled = Yes
    target_host = {backbone_host}
    target_port = {backbone_port}
"""

# Operator-added extra interfaces (Settings tab -> "Extra interfaces").
# Only these three types are emitted; the fields listed are the ones each
# needs. An unknown type, a malformed entry, a reserved/duplicate name or
# a missing field is SKIPPED WITH A WARNING, never raised -- this runs as
# rnsd's ExecStartPre, so a crash here means rnsd won't start at all.
_EXTRA_INTERFACE_FIELDS = {
    "TCPClientInterface": ("target_host", "target_port"),
    "TCPServerInterface": ("listen_ip", "listen_port"),
    "UDPInterface": ("listen_ip", "listen_port", "forward_ip", "forward_port"),
}
_RESERVED_INTERFACE_NAMES = {
    "default interface", "rnode lora", "reticulumnet internet",
}


def _sanitise_interface_name(name, used: set) -> str | None:
    name = str(name or "").strip().replace("[", "").replace("]", "").strip()
    if not name or name.lower() in _RESERVED_INTERFACE_NAMES or name in used:
        return None
    used.add(name)
    return name


def _extra_interface_blocks(entries) -> str:
    """``[[name]]`` blocks for a list of extra-interface dicts. Never
    raises; a bad entry is dropped with a printed warning."""
    if not isinstance(entries, list):
        return ""
    blocks: list[str] = []
    used_names: set = set()
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        if entry.get("enabled") is False:
            continue
        itype = str(entry.get("type") or "").strip()
        fields = _EXTRA_INTERFACE_FIELDS.get(itype)
        if fields is None:
            print(f"reticulum: skipping extra interface -- unknown type {itype!r}")
            continue
        name = _sanitise_interface_name(entry.get("name") or itype, used_names)
        if name is None:
            print(f"reticulum: skipping extra interface {entry.get('name')!r} "
                  f"-- empty, reserved or duplicate name")
            continue
        lines = [f"\n  [[{name}]]", f"    type = {itype}", "    enabled = Yes"]
        missing = [f for f in fields if entry.get(f) in (None, "")]
        if missing:
            print(f"reticulum: skipping extra interface {name!r} -- missing {', '.join(missing)}")
            continue
        for f in fields:
            lines.append(f"    {f} = {entry[f]}")
        blocks.append("\n".join(lines) + "\n")
    return "".join(blocks)


_DEFAULTS = {
    "reticulum_config_dir": "data/reticulum/rns_config",
    "rnode_enabled": False,
    "rnode_serial_port": "",
    "rnode_frequency_hz": None,
    "rnode_bandwidth_hz": 125_000,
    "rnode_tx_power": 7,
    "rnode_spreading_factor": 7,
    "rnode_coding_rate": 5,
    "backbone_enabled": False,
    "backbone_host": "",
    "backbone_port": 4242,
}


def render_config(config: dict) -> str:
    """Render only explicitly enabled interfaces. No implicit LAN discovery."""
    cfg = {**_DEFAULTS, **config}
    for key in ("rnode_serial_port", "backbone_host"):
        if any(c in str(cfg.get(key, "")) for c in ("\n", "\r", "[", "]", "#")):
            raise ValueError("Interface values must be a single configuration value")
    for interface in cfg.get("extra_interfaces", []):
        for value in interface.values():
            if isinstance(value, str) and any(c in value for c in ("\n", "\r", "[", "]", "#")):
                raise ValueError("Extra interface values must be a single configuration value")
    if cfg.get("rnode_enabled") and not str(cfg.get("rnode_serial_port", "")).strip():
        raise ValueError("Select an RNode serial port before enabling its interface")
    if cfg.get("backbone_enabled") and not str(cfg.get("backbone_host", "")).strip():
        raise ValueError("Enter a backbone host before enabling its interface")
    if cfg.get("rnode_enabled") and not cfg.get("rnode_frequency_hz"):
        raise ValueError("Choose an RNode frequency for this region before enabling RF")
    limits = []
    for term in ("short", "long"):
        value = cfg.get("rnode_airtime_limit_" + term)
        if value is not None:
            if isinstance(value, bool) or not 0 < float(value) <= 100:
                raise ValueError("Airtime limits must be greater than 0 and at most 100 percent")
            limits.append(f"    airtime_limit_{term} = {float(value):g}\n")
    cfg["airtime_block"] = "".join(limits)
    return _TEMPLATE.format(
        rnode_block=_RNODE_TEMPLATE.format(**cfg) if cfg.get("rnode_enabled") else "",
        backbone_block=_BACKBONE_TEMPLATE.format(**cfg) if cfg.get("backbone_enabled") else "",
        extra_block=_extra_interface_blocks(cfg.get("extra_interfaces", [])),
    )
