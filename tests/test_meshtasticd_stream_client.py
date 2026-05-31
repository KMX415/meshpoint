"""Tests for locked meshtasticd TCP client."""

import threading
import unittest
from unittest.mock import MagicMock, patch

from meshtastic.tcp_interface import TCPInterface

from src.capture.meshtasticd_stream_client import LockedTCPInterface


class TestLockedTCPInterface(unittest.TestCase):
    @patch.object(LockedTCPInterface, "__init__", lambda self, *args, **kwargs: None)
    def test_write_acquires_lock(self):
        iface = LockedTCPInterface.__new__(LockedTCPInterface)
        iface._stream_lock = threading.RLock()
        acquired = []

        def _write(_b):
            acquired.append(True)
            return None

        with patch.object(TCPInterface, "_writeBytes", side_effect=_write):
            iface._writeBytes(b"abc")

        self.assertTrue(acquired)


if __name__ == "__main__":
    unittest.main()
