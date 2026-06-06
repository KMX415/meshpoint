"""Release channels exposed to the dashboard update picker.

A ``ReleaseChannel`` is a logical pointer to a git ref the dashboard
allows the operator to pin to. The catalog is intentionally tiny:
``main`` (stable), the active feature branch (RC), and a fallback
``custom`` slot the user fills in by typing a branch name.

**Release housekeeping:** when bumping ``__version__`` on ``main``, replace
the RC row here for the *next* sprint (``rc-076`` / ``feat/v0.7.6``, etc.)
and branch ``feat/v0.7.N`` from updated ``main``. Full checklist:
``Meshradar.io/.cursor/rules/operations-runbook.mdc`` (Dashboard release
channel picker).

The registry lives behind a class so future versions can hot-load
extra tracks (``preview``, ``rake-back``, etc.) without touching the
route signature or the frontend payload.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Iterable


TIER_STABLE = "stable"
TIER_RC = "rc"
TIER_EXPERIMENTAL = "experimental"
TIER_CUSTOM = "custom"

# Remap retired picker ids (sessionStorage, docs, old bookmarks).
CHANNEL_ID_ALIASES: dict[str, str] = {
    "rc-074": "rc-075",
    "rc-075": "rc-076",
    "rc-076": "rc-077",
}


def normalize_channel_id(channel_id: str | None) -> str | None:
    """Return the current catalog id for a stored or requested channel id."""
    if not channel_id:
        return channel_id
    seen: set[str] = set()
    current = channel_id
    while current in CHANNEL_ID_ALIASES and current not in seen:
        seen.add(current)
        current = CHANNEL_ID_ALIASES[current]
    return current


@dataclass(frozen=True)
class ReleaseChannel:
    """One option in the release-channel picker."""

    id: str
    label: str
    branch: str
    tier: str
    description: str

    def to_dict(self) -> dict:
        return asdict(self)


DEFAULT_CHANNELS: tuple[ReleaseChannel, ...] = (
    ReleaseChannel(
        id="stable",
        label="Stable (main)",
        branch="main",
        tier=TIER_STABLE,
        description="Latest tagged release. Recommended for production gateways.",
    ),
    ReleaseChannel(
        id="rc-077",
        label="Release candidate (v0.7.7)",
        branch="feat/v0.7.7",
        tier=TIER_RC,
        description="Sprint branch for v0.7.7. Expect rough edges.",
    ),
    ReleaseChannel(
        id="wismesh-node",
        label="Experimental: WisMesh Node (RAK6421 HAT)",
        branch="feat/wismesh-hat",
        tier=TIER_EXPERIMENTAL,
        description=(
            "meshtasticd Node platform for the RAK6421 WisMesh Pi HAT. "
            "Not for RAK V2, SenseCap M1, Chameleon, or other SX1302 gateways. "
            "See docs/WISMESH-NODE.md."
        ),
    ),
    ReleaseChannel(
        id="custom",
        label="Custom branch",
        branch="",
        tier=TIER_CUSTOM,
        description="Pin to an arbitrary branch by name. Advanced users only.",
    ),
)


class ReleaseChannelRegistry:
    """Lookup helper around the channel tuple."""

    def __init__(self, channels: Iterable[ReleaseChannel] = DEFAULT_CHANNELS) -> None:
        self._channels: tuple[ReleaseChannel, ...] = tuple(channels)

    def channels(self) -> tuple[ReleaseChannel, ...]:
        return self._channels

    def to_payload(self) -> list[dict]:
        return [c.to_dict() for c in self._channels]

    def find(self, channel_id: str) -> ReleaseChannel | None:
        channel_id = normalize_channel_id(channel_id) or ""
        for channel in self._channels:
            if channel.id == channel_id:
                return channel
        return None

    def rc_channel(self) -> ReleaseChannel | None:
        """Return the configured release-candidate channel, if any."""
        for channel in self._channels:
            if channel.tier == TIER_RC:
                return channel
        return None

    def resolve_branch(
        self, channel_id: str, *, custom_branch: str | None = None
    ) -> str | None:
        """Return the git branch the channel maps to.

        For the ``custom`` tier the caller must supply
        ``custom_branch``; we still validate that the value is a
        plausible branch name (no whitespace, no shell metachars) so
        the call site can simply trust the return value.
        """
        channel = self.find(normalize_channel_id(channel_id) or channel_id)
        if channel is None:
            return None
        if channel.tier == TIER_CUSTOM:
            if not custom_branch or not _is_safe_branch(custom_branch):
                return None
            return custom_branch
        return channel.branch


_BRANCH_DISALLOWED = set(" \t\n\r;|&`$()<>")


def _is_safe_branch(name: str) -> bool:
    if not name or len(name) > 200:
        return False
    if any(ch in _BRANCH_DISALLOWED for ch in name):
        return False
    if name.startswith("-"):
        return False
    return True
