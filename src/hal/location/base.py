"""Abstract base class for location sources.

Every concrete source (``StaticSource``, ``GpsdSource``, ``UartSource``)
implements the same lifecycle: ``start`` / ``stop`` / ``get_status``.
The coordinator owns the lifecycle; route handlers and the WebSocket
broadcaster only ever read ``get_status()``.

Why an abstract base over duck typing: keeps the contract explicit,
gives mypy/IDE help, and makes the factory easy to test (every branch
returns the same protocol).
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from src.hal.location.models import GpsStatus


class LocationSource(ABC):
    """Pluggable provider of GPS-style positional data."""

    @property
    @abstractmethod
    def source_name(self) -> str:
        """Stable label: ``"static"`` | ``"gpsd"`` | ``"uart"``."""

    @abstractmethod
    async def start(self) -> None:
        """Begin acquiring fixes. Idempotent: safe to call twice."""

    @abstractmethod
    async def stop(self) -> None:
        """Release resources. Idempotent: safe to call twice or unstarted."""

    @abstractmethod
    def get_status(self) -> GpsStatus:
        """Return the latest status snapshot.

        Always returns a non-``None`` ``GpsStatus``. ``available=False``
        on the result means "source initialized but not currently
        providing live data" (e.g. gpsd offline, no fix yet); callers
        decide how to render that.
        """
