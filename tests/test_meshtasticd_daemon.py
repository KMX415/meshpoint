"""Tests for meshtasticd daemon helpers."""

import unittest
from unittest.mock import MagicMock, patch

from src.capture import meshtasticd_daemon


class TestMeshtasticdDaemon(unittest.TestCase):
    @patch("src.capture.meshtasticd_daemon.subprocess.run")
    def test_is_service_active_true(self, mock_run):
        mock_run.return_value.stdout = "active\n"
        mock_run.return_value.returncode = 0
        self.assertTrue(meshtasticd_daemon.is_service_active())
        mock_run.assert_called_with(
            ["sudo", "/usr/bin/systemctl", "is-active", "meshtasticd"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )

    @patch("src.capture.meshtasticd_daemon._wait_for_tcp_port")
    @patch("src.capture.meshtasticd_daemon.is_service_active", return_value=True)
    @patch("src.capture.meshtasticd_daemon.subprocess.run")
    def test_restart_service_and_wait(self, mock_run, _active, mock_wait):
        mock_run.return_value.returncode = 0
        meshtasticd_daemon.restart_service_and_wait("127.0.0.1", 4403)
        mock_run.assert_called_once()
        mock_wait.assert_called_once_with("127.0.0.1", 4403)

    @patch("src.capture.meshtasticd_daemon.socket.create_connection")
    def test_wait_for_tcp_port_success(self, mock_conn):
        mock_conn.return_value.__enter__ = MagicMock(return_value=None)
        mock_conn.return_value.__exit__ = MagicMock(return_value=False)
        meshtasticd_daemon._wait_for_tcp_port("127.0.0.1", 4403)


if __name__ == "__main__":
    unittest.main()
