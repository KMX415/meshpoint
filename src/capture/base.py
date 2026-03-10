from __future__ import annotations

from abc import ABC, abstractmethod
from typing import AsyncIterator

from src.models.packet import RawCapture


class CaptureSource(ABC):
    """Abstract base for all packet capture sources.

    Implementations must provide an async iterator of RawCapture objects.
    Each source runs independently and yields captured packets as they arrive.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable source name (e.g. 'concentrator', 'serial')."""
        ...

    @abstractmethod
    async def start(self) -> None:
        """Initialize hardware/connection and prepare for capture."""
        ...

    @abstractmethod
    async def stop(self) -> None:
        """Clean up resources and stop capturing."""
        ...

    @abstractmethod
    async def packets(self) -> AsyncIterator[RawCapture]:
        """Yield captured packets as they are received."""
        ...
        yield  # pragma: no cover

    @property
    def is_running(self) -> bool:
        return False
