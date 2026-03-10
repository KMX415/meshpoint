#!/usr/bin/env python3
"""
WiFi network watchdog for Mesh Point.

Standalone service (no meshpoint imports, stdlib only) that:
  1. Disables WiFi power save on startup
  2. Pings the default gateway every CHECK_INTERVAL seconds
  3. Escalates recovery on consecutive failures:
     - Stage 1: restart the wlan interface
     - Stage 2: full system reboot
"""

from __future__ import annotations

import logging
import subprocess
import sys
import time

WIFI_INTERFACE = "wlan0"
CHECK_INTERVAL_SECONDS = 120
RESTART_THRESHOLD = 3
REBOOT_THRESHOLD = 6
PING_TIMEOUT_SECONDS = 5
FALLBACK_PING_TARGET = "8.8.8.8"

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("network-watchdog")


class ConnectivityProbe:
    """Checks reachability of the default gateway via ICMP ping."""

    def __init__(self, timeout_seconds: int = PING_TIMEOUT_SECONDS) -> None:
        self._timeout = timeout_seconds

    def check(self) -> bool:
        target = self._detect_gateway() or FALLBACK_PING_TARGET
        return self._ping(target)

    def _ping(self, target: str) -> bool:
        try:
            result = subprocess.run(
                ["ping", "-c", "1", "-W", str(self._timeout), target],
                capture_output=True,
                timeout=self._timeout + 5,
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, OSError):
            return False

    @staticmethod
    def _detect_gateway() -> str | None:
        """Parse /proc/net/route for the default gateway IP."""
        try:
            with open("/proc/net/route") as fh:
                for line in fh:
                    fields = line.strip().split()
                    if len(fields) >= 3 and fields[1] == "00000000":
                        packed = int(fields[2], 16)
                        return ".".join(
                            str((packed >> (8 * i)) & 0xFF) for i in range(4)
                        )
        except (OSError, ValueError):
            pass
        return None


class NetworkWatchdog:
    """Main watchdog loop with escalating WiFi recovery."""

    def __init__(self) -> None:
        self._probe = ConnectivityProbe()
        self._consecutive_failures = 0

    def run(self) -> None:
        logger.info("Starting network watchdog (interface=%s)", WIFI_INTERFACE)
        self._disable_power_save()

        while True:
            time.sleep(CHECK_INTERVAL_SECONDS)
            self._tick()

    def _tick(self) -> None:
        if self._probe.check():
            if self._consecutive_failures > 0:
                logger.info(
                    "Connectivity restored after %d failures",
                    self._consecutive_failures,
                )
            self._consecutive_failures = 0
            return

        self._consecutive_failures += 1
        logger.warning(
            "Connectivity check failed (%d consecutive)", self._consecutive_failures
        )

        if self._consecutive_failures >= REBOOT_THRESHOLD:
            self._reboot()
        elif self._consecutive_failures >= RESTART_THRESHOLD:
            self._restart_interface()

    def _disable_power_save(self) -> None:
        logger.info("Disabling WiFi power save on %s", WIFI_INTERFACE)
        self._run_quiet(["iw", "dev", WIFI_INTERFACE, "set", "power_save", "off"])

    def _restart_interface(self) -> None:
        logger.warning("Stage 1 recovery: restarting %s", WIFI_INTERFACE)
        self._run_quiet(["ip", "link", "set", WIFI_INTERFACE, "down"])
        time.sleep(2)
        self._run_quiet(["ip", "link", "set", WIFI_INTERFACE, "up"])

    def _reboot(self) -> None:
        logger.critical(
            "Stage 2 recovery: rebooting after %d consecutive failures",
            self._consecutive_failures,
        )
        self._run_quiet(["systemctl", "reboot"])

    @staticmethod
    def _run_quiet(cmd: list[str]) -> None:
        try:
            subprocess.run(cmd, capture_output=True, timeout=15)
        except (subprocess.TimeoutExpired, OSError) as exc:
            logger.error("Command %s failed: %s", cmd, exc)


def main() -> None:
    try:
        NetworkWatchdog().run()
    except KeyboardInterrupt:
        logger.info("Watchdog stopped")
        sys.exit(0)


if __name__ == "__main__":
    main()
