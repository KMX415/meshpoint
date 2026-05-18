"""Release channels exposed to the dashboard update picker.

A ``ReleaseChannel`` is a logical pointer to a git ref the dashboard
allows the operator to pin to. The catalog is intentionally tiny:
``main`` (stable), the active feature branch (RC), and a fallback
``custom`` slot the user fills in by typing a branch name.

The registry lives behind a class so future versions can hot-load
extra tracks (``preview``, ``rake-back``, etc.) without touching the
route signature or the frontend payload.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Iterable


TIER_STABLE = "stable"
TIER_RC = "rc"
TIER_CUSTOM = "custom"


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
        id="rc-074",
        label="Release candidate (v0.7.4)",
        branch="feat/v0.7.4",
        tier=TIER_RC,
        description="Sprint branch for v0.7.4. Expect rough edges.",
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
        for channel in self._channels:
            if channel.id == channel_id:
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
        channel = self.find(channel_id)
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
