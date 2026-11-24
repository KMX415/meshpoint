"""Shared "who owns the RTL-SDR dongle" registry.

A single physical RTL-SDR dongle can only be tuned to one frequency by
one process at a time. RtlListener (FM/RDS, src/audio/rtl_listener.py)
and PagerListener (P2000/Pagers, src/audio/pager_listener.py) are
otherwise fully independent, but must not both try to open the dongle
simultaneously -- a second rtl_fm would simply fail to open the device.

Manual-stop-required by design (2026-07-12): switching tabs while
another listener is active is rejected with a clear error instead of
silently killing whatever was running, so a user never loses an
in-progress recording/listen without knowing why.
"""

from __future__ import annotations

_owner: str | None = None


def claim(name: str) -> None:
    """Claim the dongle for *name*.

    No-op if *name* already owns it (idempotent retune/retry). Raises
    RuntimeError if a different listener currently owns it.
    """
    global _owner
    if _owner is not None and _owner != name:
        raise RuntimeError(
            f"RTL-SDR dongle is in use by '{_owner}' -- stop it first"
        )
    _owner = name


def release(name: str) -> None:
    """Release the dongle if *name* currently owns it.

    No-op if some other listener holds it (or nobody does) -- a stale
    release must never clear someone else's active claim.
    """
    global _owner
    if _owner == name:
        _owner = None


def current_owner() -> str | None:
    return _owner
