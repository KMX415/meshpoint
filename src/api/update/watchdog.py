"""Health-poll watchdog for dashboard-driven updates.

After a successful :class:`UpdateApplier.apply`, the dashboard
records the previous commit SHA as a :class:`RollbackTag` and starts
a watchdog that pings the local API for ``poll_count`` iterations.
If the new build fails to come up healthy within the budget, the
watchdog calls :meth:`UpdateApplier.rollback` and emits an audit log
entry. Phase 2 wires this loop into the lifespan so manual restarts
are no longer required for an unhealthy upgrade.

The class is intentionally framework-free so it is easy to unit
test: callers inject a synchronous ``probe`` callable that returns
``True`` when the dashboard is healthy. Async wiring lives in the
route layer where the asyncio event loop is already available.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Callable, Optional

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RollbackTag:
    """Snapshot of the install tree state pre-update."""

    sha: str
    branch: str
    captured_at: float


HealthProbe = Callable[[], bool]
RollbackHandler = Callable[[str], None]


class WatchdogMonitor:
    """Decide whether to roll back after an apply.

    Calls ``probe`` repeatedly with ``poll_interval_seconds`` between
    samples. Healthy state is reached after ``healthy_streak`` true
    returns in a row -- one good probe is not enough because the
    service may flap during restart. If the budget runs out before
    a healthy streak lands, ``rollback_handler`` is invoked with the
    pre-update SHA and the watchdog reports failure.
    """

    def __init__(
        self,
        *,
        probe: HealthProbe,
        rollback_handler: RollbackHandler,
        poll_interval_seconds: float = 5.0,
        max_polls: int = 24,
        healthy_streak: int = 3,
        sleep_func: Callable[[float], None] = time.sleep,
    ) -> None:
        self._probe = probe
        self._rollback_handler = rollback_handler
        self._poll_interval = poll_interval_seconds
        self._max_polls = max_polls
        self._healthy_streak = healthy_streak
        self._sleep = sleep_func

    def watch(self, tag: RollbackTag) -> bool:
        """Block until the new build is healthy or roll back."""
        streak = 0
        for poll in range(self._max_polls):
            try:
                healthy = bool(self._probe())
            except Exception:
                logger.debug("health probe raised", exc_info=True)
                healthy = False
            if healthy:
                streak += 1
                if streak >= self._healthy_streak:
                    logger.info(
                        "watchdog: healthy after %d polls (streak=%d)",
                        poll + 1, streak,
                    )
                    return True
            else:
                streak = 0
            self._sleep(self._poll_interval)
        logger.warning(
            "watchdog: budget exhausted, rolling back to %s", tag.sha,
        )
        try:
            self._rollback_handler(tag.sha)
        except Exception:
            logger.exception("watchdog rollback handler failed")
        return False


def make_rollback_tag(
    sha: Optional[str], *, branch: str = "",
) -> Optional[RollbackTag]:
    """Build a :class:`RollbackTag`; returns ``None`` if no SHA."""
    if not sha:
        return None
    return RollbackTag(sha=sha, branch=branch, captured_at=time.time())
