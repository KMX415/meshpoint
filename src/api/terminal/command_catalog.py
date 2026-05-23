"""Declarative one-click command catalog for the web terminal.

Each entry is a ``CommandEntry`` describing a button the dashboard
renders next to the live shell. The button does **not** sandbox the
command -- the operator is admin and the shell is full -- it just
saves them from re-typing the obvious diagnostic incantations
(service tail, disk free, journal of meshpoint, etc.).

The catalog is a frozen dataclass list so it serializes cleanly to
JSON for ``GET /api/terminal/commands`` and so an MCP-style review
of available commands is one read of this file.

Categories are display-only; the frontend groups buttons by
category in the command guide drawer. Adding a new command means:

1. Append a ``CommandEntry`` to ``DEFAULT_CATALOG``.
2. Pick the closest existing category, or add a new one.
3. Mark ``dangerous=True`` if the command can leave the host in a
   bad state (service stop, db wipe, reboot). Frontend uses that
   flag to require a typed-name confirmation before insertion.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Iterable


CATEGORY_SERVICE = "Service"
CATEGORY_LOGS = "Logs"
CATEGORY_DIAGNOSTICS = "Diagnostics"
CATEGORY_HARDWARE = "Hardware"
CATEGORY_GIT = "Git"
CATEGORY_NETWORK = "Network"


@dataclass(frozen=True)
class CommandEntry:
    """One curated command surfaced as a button in the terminal UI.

    ``command`` is inserted verbatim at the prompt. The frontend may
    still let the operator edit it before pressing Enter; the
    catalog is a starting point, not a sandbox.
    """

    id: str
    label: str
    command: str
    category: str
    description: str
    dangerous: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


DEFAULT_CATALOG: tuple[CommandEntry, ...] = (
    CommandEntry(
        id="service-status",
        label="Service status",
        command="sudo systemctl status meshpoint --no-pager",
        category=CATEGORY_SERVICE,
        description="Show the current meshpoint service state.",
    ),
    CommandEntry(
        id="service-restart",
        label="Restart service",
        command="sudo systemctl restart meshpoint",
        category=CATEGORY_SERVICE,
        description="Restart the meshpoint service.",
        dangerous=True,
    ),
    CommandEntry(
        id="meshpoint-logs",
        label="Live logs (meshpoint logs)",
        command="meshpoint logs",
        category=CATEGORY_LOGS,
        description="Live-tail the service log via the CLI wrapper; Ctrl-C to stop.",
    ),
    CommandEntry(
        id="journal-tail",
        label="Tail journal (100 lines)",
        command="journalctl -u meshpoint -n 100 --no-pager",
        category=CATEGORY_LOGS,
        description="Last 100 log lines from the service.",
    ),
    CommandEntry(
        id="journal-follow",
        label="Follow journal",
        command="journalctl -u meshpoint -f",
        category=CATEGORY_LOGS,
        description="Live-tail the raw journal; Ctrl-C to stop.",
    ),
    CommandEntry(
        id="disk-free",
        label="Disk free",
        command="df -h",
        category=CATEGORY_DIAGNOSTICS,
        description="Show filesystem usage.",
    ),
    CommandEntry(
        id="memory",
        label="Memory",
        command="free -h",
        category=CATEGORY_DIAGNOSTICS,
        description="Show memory usage.",
    ),
    CommandEntry(
        id="cpu-temp",
        label="CPU temperature",
        command="vcgencmd measure_temp 2>/dev/null || cat /sys/class/thermal/thermal_zone0/temp",
        category=CATEGORY_DIAGNOSTICS,
        description="SoC temperature in degrees C.",
    ),
    CommandEntry(
        id="lsusb",
        label="USB devices",
        command="lsusb",
        category=CATEGORY_HARDWARE,
        description="Connected USB peripherals.",
    ),
    CommandEntry(
        id="lsblk",
        label="Block devices",
        command="lsblk",
        category=CATEGORY_HARDWARE,
        description="Storage devices and partitions.",
    ),
    CommandEntry(
        id="ip-addr",
        label="Network interfaces",
        command="ip -brief addr",
        category=CATEGORY_NETWORK,
        description="IP addresses on each interface.",
    ),
    CommandEntry(
        id="git-status",
        label="Git status",
        command="cd /opt/meshpoint && sudo git status",
        category=CATEGORY_GIT,
        description="Repository state for the install tree.",
    ),
    CommandEntry(
        id="git-log",
        label="Git log (10)",
        command="cd /opt/meshpoint && sudo git log -n 10 --oneline",
        category=CATEGORY_GIT,
        description="Last 10 commits on the install tree.",
    ),
)


class CommandCatalog:
    """In-memory wrapper exposing the catalog as JSON-friendly dicts.

    Wrapping a frozen tuple in a class lets future extensions
    (per-host overlays, plugin-contributed entries) be additive
    without changing the route signature.
    """

    def __init__(self, entries: Iterable[CommandEntry] = DEFAULT_CATALOG) -> None:
        self._entries: tuple[CommandEntry, ...] = tuple(entries)

    def entries(self) -> tuple[CommandEntry, ...]:
        return self._entries

    def to_payload(self) -> list[dict]:
        return [entry.to_dict() for entry in self._entries]

    def categories(self) -> list[str]:
        seen: list[str] = []
        for entry in self._entries:
            if entry.category not in seen:
                seen.append(entry.category)
        return seen

    def find(self, entry_id: str) -> CommandEntry | None:
        for entry in self._entries:
            if entry.id == entry_id:
                return entry
        return None
