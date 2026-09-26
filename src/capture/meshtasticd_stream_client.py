"""Thread-safe TCPInterface for meshtasticd phone API."""

from __future__ import annotations

import contextlib
import logging
import socket
import threading

from meshtastic.tcp_interface import TCPInterface

logger = logging.getLogger(__name__)

_DEFAULT_CLOSE_TIMEOUT_SECONDS = 5.0


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

    def close(self, *, join_timeout: float = _DEFAULT_CLOSE_TIMEOUT_SECONDS) -> None:
        force_close_tcp_interface(self, join_timeout=join_timeout)


def force_close_tcp_interface(
    iface: TCPInterface,
    *,
    join_timeout: float = _DEFAULT_CLOSE_TIMEOUT_SECONDS,
) -> None:
    """Close a TCPInterface without blocking forever on a stuck reader thread."""
    iface._wantExit = True  # noqa: SLF001 — meshtastic stream API
    sock = getattr(iface, "socket", None)
    if sock is not None:
        with contextlib.suppress(OSError):
            sock.shutdown(socket.SHUT_RDWR)
        with contextlib.suppress(OSError):
            sock.close()
        iface.socket = None  # noqa: SLF001

    rx_thread = getattr(iface, "_rxThread", None)
    if (
        rx_thread is not None
        and rx_thread is not threading.current_thread()
        and rx_thread.is_alive()
    ):
        rx_thread.join(timeout=join_timeout)
        if rx_thread.is_alive():
            logger.warning(
                "meshtasticd reader thread did not exit within %.0fs; abandoning",
                join_timeout,
            )

    try:
        from meshtastic.mesh_interface import MeshInterface

        MeshInterface.close(iface)
    except Exception:
        logger.debug("meshtasticd MeshInterface.close failed", exc_info=True)
