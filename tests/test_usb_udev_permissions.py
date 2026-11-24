"""Exercise installer migration blocks with temporary rules and fake host commands."""
from __future__ import annotations

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASH = shutil.which("bash")
if BASH is None:
    candidate = Path("C:/Program Files/Git/bin/bash.exe")
    BASH = str(candidate) if candidate.exists() else None
OLD = 'SUBSYSTEM=="tty", ATTRS{idVendor}=="303a", MODE="0666"'
NEW = 'SUBSYSTEM=="tty", ATTRS{idVendor}=="303a", MODE="0660", GROUP="dialout"'


@unittest.skipUnless(BASH, "bash is needed for shell migration tests")
class TestUsbUdevPermissions(unittest.TestCase):
    def _run(self, script, initial, *, groups="meshpoint dialout", usermod_status=0):
        source = (ROOT / "scripts" / script).read_text(encoding="utf-8")
        if script == "install.sh":
            block = source[source.index("# Espressif USB nodes"):source.index("# Allow service user")]
        else:
            start = source.index("# Tighten the old bundled Espressif rule")
            block = source[start:source.index('if [ -f "$HAL_SRC" ]', start)]
        # Only the USB block runs. No installer, HAL, sudoers or real udev calls.
        block = block.replace("/etc/udev/rules.d/99-meshpoint-esp.rules", "rule")
        stub = (
            'set -e\nCHANGED=0\ninfo() { :; }\n'
            f'id() {{ echo "{groups}"; }}\n'
            f'usermod() {{ echo usermod >> calls; return {usermod_status}; }}\n'
            'udevadm() { echo udevadm >> calls; }\n'
        )
        with tempfile.TemporaryDirectory() as tmp:
            rule = Path(tmp) / "rule"
            if initial is not None:
                rule.write_text(initial + "\n", encoding="utf-8")
            result = subprocess.run(
                [BASH, "--noprofile", "--norc", "-s"], input=(stub + block).encode("utf-8"),
                cwd=tmp, capture_output=True, timeout=10,
            )
            content = rule.read_text().strip() if rule.exists() else None
            calls_path = Path(tmp) / "calls"
            calls = calls_path.read_text().splitlines() if calls_path.exists() else []
            return result, content, calls

    def test_fresh_install_creates_restricted_rule(self):
        result, content, calls = self._run("install.sh", None)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(content, NEW)
        self.assertEqual(calls, ["udevadm", "udevadm"])

    def test_old_rule_migrates_and_second_run_is_noop(self):
        for script in ("install.sh", "post_update.sh"):
            with self.subTest(script=script):
                result, content, calls = self._run(script, OLD, groups="meshpoint")
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(content, NEW)
                self.assertEqual(calls, ["usermod", "udevadm", "udevadm"])
                result, content, calls = self._run(script, content)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(content, NEW)
                self.assertEqual(calls, [])

    def test_custom_rule_is_preserved(self):
        custom = OLD + ', GROUP="operator"'
        for script in ("install.sh", "post_update.sh"):
            with self.subTest(script=script):
                result, content, calls = self._run(script, custom)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(content, custom)
                self.assertEqual(calls, [])

    def test_failed_group_update_leaves_old_access_intact(self):
        for script in ("install.sh", "post_update.sh"):
            with self.subTest(script=script):
                result, content, calls = self._run(
                    script, OLD, groups="meshpoint", usermod_status=1,
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(content, OLD)
                self.assertEqual(calls, ["usermod"])

    def test_update_without_rule_is_noop(self):
        result, content, calls = self._run("post_update.sh", None)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIsNone(content)
        self.assertEqual(calls, [])


if __name__ == "__main__":
    unittest.main()
