"""Dashboard-driven update subsystem.

The legacy ``/api/device/update-check`` endpoint stays in place to
keep the existing sidebar badge ticking. v0.7.4 adds a more powerful
flow:

* ``Channels`` enumerate the release tracks an operator can pin to
  (``main``, ``feat/v0.7.4``, custom branch). Each carries a label,
  description, and stability tier so the UI can warn when the user
  picks something risky.
* ``UpdateApplier`` performs ``git fetch`` + ``git checkout -f`` +
  ``git reset --hard origin/<branch>`` +
  ``bash scripts/install.sh`` + ``systemctl restart meshpoint`` in
  sequence, capturing stdout/stderr for the dashboard log pane.
* ``WatchdogMonitor`` polls the API after a successful apply; if
  the new build never reaches the healthy state, the operator gets a
  rollback button (Phase 2 ships the auto-rollback wiring).

Public surface lands in ``routes.py``; the implementation modules
stay focused so each can be unit-tested without spinning up a real
shell. ``apply.py`` accepts an injected ``Runner`` so tests can
swap in a fake subprocess invoker.
"""

from src.api.update.channels import (
    DEFAULT_CHANNELS,
    ReleaseChannel,
    ReleaseChannelRegistry,
)
from src.api.update.apply import (
    ApplyAttempt,
    ApplyResult,
    Runner,
    StreamCallback,
    UpdateApplier,
)
from src.api.update.release_notes import (
    ChangelogBullet,
    ChangelogParser,
    ChangelogSection,
    select_preview_section,
)
from src.api.update.watchdog import RollbackTag, WatchdogMonitor

__all__ = [
    "ApplyAttempt",
    "ApplyResult",
    "ChangelogBullet",
    "ChangelogParser",
    "ChangelogSection",
    "DEFAULT_CHANNELS",
    "ReleaseChannel",
    "ReleaseChannelRegistry",
    "RollbackTag",
    "Runner",
    "StreamCallback",
    "UpdateApplier",
    "WatchdogMonitor",
    "select_preview_section",
]
