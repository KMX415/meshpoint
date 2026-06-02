"""WisBlock module presets for the RAK6421 WisMesh HAT (meshtasticd config.d)."""

from __future__ import annotations

import logging
import re
from dataclasses import asdict, dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

MESHTASTICD_CONFIGD = Path("/etc/meshtasticd/config.d")
MESHTASTICD_AVAILABLE = Path("/etc/meshtasticd/available.d")
RAK6421_GLOB = "lora-RAK6421-*.yaml"

_CS_UNCOMMENT = re.compile(
    r"^([ \t]*)#([ \t]*CS:)",
    re.MULTILINE,
)


@dataclass(frozen=True)
class WisBlockModulePreset:
    """One WisBlock LoRa module profile shipped for the RAK6421 HAT."""

    module_id: str
    label: str
    tagline: str
    filename: str
    tx_class: str

    def to_dict(self, *, active: bool = False) -> dict:
        payload = asdict(self)
        payload["active"] = active
        return payload


MODULE_CATALOG: tuple[WisBlockModulePreset, ...] = (
    WisBlockModulePreset(
        module_id="13302",
        label="RAK13302 1W",
        tagline="High-power WisBlock with SKY66122 PA (~30 dBm class)",
        filename="lora-RAK6421-13302-slot1.yaml",
        tx_class="1W PA",
    ),
    WisBlockModulePreset(
        module_id="13300",
        label="RAK13300",
        tagline="Standard-power WisBlock (~22 dBm)",
        filename="lora-RAK6421-13300-slot1.yaml",
        tx_class="standard",
    ),
)

_BY_ID = {entry.module_id: entry for entry in MODULE_CATALOG}
_BY_FILENAME = {entry.filename: entry for entry in MODULE_CATALOG}


def meshpoint_root() -> Path:
    import os

    env = os.environ.get("MESHPOINT_DIR", "").strip()
    if env:
        return Path(env)
    return Path(__file__).resolve().parents[2]


def bundled_preset_path(filename: str, root: Path | None = None) -> Path:
    base = root or meshpoint_root()
    return base / "config" / "meshtasticd" / filename


def module_id_from_preset_filename(filename: str) -> str:
    entry = _BY_FILENAME.get(filename or "")
    if entry is not None:
        return entry.module_id
    lowered = (filename or "").lower()
    if "13302" in lowered:
        return "13302"
    if "13300" in lowered:
        return "13300"
    return ""


def list_module_presets(active_filename: str = "") -> list[dict]:
    active = active_filename or ""
    return [
        entry.to_dict(active=entry.filename == active)
        for entry in MODULE_CATALOG
    ]


def resolve_module_preset(module_id: str) -> WisBlockModulePreset:
    key = (module_id or "").strip()
    entry = _BY_ID.get(key)
    if entry is None:
        raise ValueError(f"Unknown WisBlock module id: {module_id!r}")
    return entry


def _find_preset_source(filename: str, root: Path) -> Path | None:
    available = MESHTASTICD_AVAILABLE / filename
    if available.is_file():
        return available
    bundled = bundled_preset_path(filename, root)
    if bundled.is_file():
        return bundled
    return None


def _uncomment_cs_pin(text: str) -> str:
    return _CS_UNCOMMENT.sub(r"\1\2", text)


def install_preset_file(filename: str, root: Path | None = None) -> None:
    """Copy one RAK6421 preset into config.d (mirrors install_meshtasticd.sh)."""
    repo = root or meshpoint_root()
    source = _find_preset_source(filename, repo)
    if source is None:
        raise FileNotFoundError(
            f"Preset {filename} not found under {MESHTASTICD_AVAILABLE} "
            f"or {repo / 'config/meshtasticd'}"
        )

    MESHTASTICD_CONFIGD.mkdir(parents=True, exist_ok=True)
    for stale in MESHTASTICD_CONFIGD.glob(RAK6421_GLOB):
        if stale.name != filename:
            stale.unlink(missing_ok=True)

    target = MESHTASTICD_CONFIGD / filename
    content = source.read_text(encoding="utf-8")
    target.write_text(_uncomment_cs_pin(content), encoding="utf-8")
    try:
        import pwd

        uid = pwd.getpwnam("meshtasticd").pw_uid
        gid = pwd.getpwnam("meshtasticd").pw_gid
        target.chown(uid, gid)
    except (ImportError, KeyError, OSError):
        pass
    logger.info("Installed meshtasticd LoRa preset: %s", filename)


def persist_preset_to_yaml(filename: str) -> None:
    import yaml

    from src.config import _get_local_yaml_path

    path = _get_local_yaml_path()
    existing: dict = {}
    if path.exists():
        with open(path, encoding="utf-8") as fh:
            existing = yaml.safe_load(fh) or {}

    capture = existing.get("capture")
    if not isinstance(capture, dict):
        capture = {}
    md = capture.get("meshtasticd")
    if not isinstance(md, dict):
        md = {}
    md["preset"] = filename
    capture["meshtasticd"] = md
    existing["capture"] = capture

    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        yaml.dump(existing, fh, default_flow_style=False, sort_keys=False)


def apply_module_preset(
    module_id: str,
    *,
    restart_meshtasticd: bool = True,
    root: Path | None = None,
    host: str = "127.0.0.1",
    port: int = 4403,
) -> dict:
    """Install yaml, persist local.yaml, restart meshtasticd."""
    entry = resolve_module_preset(module_id)
    install_preset_file(entry.filename, root=root)
    persist_preset_to_yaml(entry.filename)

    if restart_meshtasticd:
        from src.capture.meshtasticd_daemon import restart_service_and_wait

        restart_service_and_wait(host=host, port=port)

    return {
        "applied": True,
        "module_id": entry.module_id,
        "preset_file": entry.filename,
        "label": entry.label,
        "meshpoint_restart_recommended": True,
    }
