"""Operations behind the Settings → Dangerous subsection.

These actions can leave the host in a degraded state if mis-fired,
so each one is gated by a typed-confirmation modal in the UI and
audited in the JSONL log on the server side. The handler classes
here have one job each and accept their dependencies through the
constructor so tests can substitute fakes.
"""

from src.api.dangerous.actions import (
    DangerousAction,
    DangerousActionRegistry,
    DangerousActionResult,
)

__all__ = [
    "DangerousAction",
    "DangerousActionRegistry",
    "DangerousActionResult",
]
