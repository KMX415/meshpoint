"""GPIO selection without loading the HAL or touching hardware."""
import os
import subprocess
import unittest
from unittest.mock import call, patch

from src.hal.sx1302_wrapper import SX1302Wrapper


class TestConcentratorReset(unittest.TestCase):
    def run_reset(self, environment, explicit=None):
        with patch.dict(os.environ, environment, clear=True), \
                patch("subprocess.run") as run, patch("time.sleep") as sleep:
            SX1302Wrapper().reset(explicit)
        return run, sleep

    def assert_pins(self, run, pins):
        expected = [call(["pinctrl", "set", str(pin), "op", level],
                         check=True, capture_output=True)
                    for level in ("dh", "dl") for pin in pins]
        self.assertEqual(run.call_args_list, expected)

    def test_absent_or_empty_override_preserves_default(self):
        for env in ({}, {"RESET_GPIO": ""}):
            with self.subTest(env=env):
                run, sleep = self.run_reset(env)
                self.assert_pins(run, [17, 25])
                self.assertEqual(sleep.call_args_list, [call(0.1), call(0.1)])

    def test_cotx_only_toggles_gpio_22(self):
        run, sleep = self.run_reset({"RESET_GPIO": "22", "CONCENTRATOR_RESET_HOLD_SEC": "0.7"})
        self.assert_pins(run, [22])
        self.assertEqual(sleep.call_args_list, [call(0.7), call(0.7)])

    def test_multiple_pins_allow_whitespace(self):
        run, _ = self.run_reset({"RESET_GPIO": " 17\t25 "})
        self.assert_pins(run, [17, 25])

    def test_explicit_pins_override_environment(self):
        for value in ("22", "invalid"):
            run, _ = self.run_reset({"RESET_GPIO": value}, [7])
            self.assert_pins(run, [7])

    def test_invalid_override_does_not_touch_any_pin(self):
        for value in (" ", "-1", "22 nope", "22,25", "1.5", "２２", "9" * 5000):
            with self.subTest(value=value[:30]), self.assertLogs("src.hal.sx1302_wrapper", level="WARNING"):
                run, sleep = self.run_reset({"RESET_GPIO": value})
                run.assert_not_called()
                sleep.assert_not_called()

    def test_gpio_tool_failures_remain_best_effort(self):
        for error in (FileNotFoundError(), subprocess.CalledProcessError(1, "pinctrl")):
            with patch.dict(os.environ, {"RESET_GPIO": "22"}, clear=True), \
                    patch("subprocess.run", side_effect=error), patch("time.sleep"), \
                    self.assertLogs("src.hal.sx1302_wrapper", level="WARNING"):
                SX1302Wrapper().reset()
