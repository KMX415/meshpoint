"""Tests for meshtasticd bridge IPC helpers."""

import unittest

from src.capture.meshtasticd_bridge_ipc import (
    fatal_message,
    fatal_reason,
    is_fatal_message,
)


class TestMeshtasticdBridgeIpc(unittest.TestCase):
    def test_fatal_message_round_trip(self):
        message = fatal_message("reader died")
        self.assertTrue(is_fatal_message(message))
        self.assertEqual(fatal_reason(message), "reader died")

    def test_non_fatal_message(self):
        self.assertFalse(is_fatal_message({"kind": "packet"}))


if __name__ == "__main__":
    unittest.main()
