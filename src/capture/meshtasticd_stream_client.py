"""Thread-safe TCPInterface for meshtasticd phone API."""

from __future__ import annotations

import threading

from meshtastic.tcp_interface import TCPInterface


class LockedTCPInterface(TCPInterface):
    """Serialize socket reads and writes across meshtastic-python threads.

    The stock TCPInterface lets the background reader thread and API callers
    (sendText, setOwner, writeConfig) touch the same socket concurrently.
    That corrupts the protobuf byte stream: meshtasticd keeps forwarding,
    but the client stops parsing live packets while the reader thread still
    appears alive.
    """

    def __init__(self, *args, **kwargs):
        self._stream_lock = threading.RLock()
        super().__init__(*args, **kwargs)

    def _writeBytes(self, b: bytes) -> None:
        with self._stream_lock:
            super()._writeBytes(b)

    def _readBytes(self, length):
        # Reader thread only: do not hold the lock across blocking recv or
        # connect()/waitForConfig() deadlocks on startup.
        return super()._readBytes(length)

    def close(self) -> None:
        with self._stream_lock:
            super().close()
