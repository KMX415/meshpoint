"""Tests for install branch detection and channel matching."""

from __future__ import annotations

import unittest
from typing import Optional
from unittest import mock

from src.api.update.channels import ReleaseChannelRegistry
from src.api.update.install_status import (
    build_install_status_payload,
    match_channel_for_branch,
    read_install_git_ref,
)


class _FakeGitRunner:
    def __init__(
        self,
        branch: str = "feat/v0.7.4",
        sha: str = "ac6895a",
    ) -> None:
        self.branch = branch
        self.sha = sha
        self.calls: list[list[str]] = []

    def __call__(
        self, args: list[str], cwd: Optional[str], timeout_seconds: float,
    ) -> tuple[int, str, str]:
        self.calls.append(list(args))
        if "rev-parse" in args and any("--abbrev-ref" in a for a in args):
            return 0, f"{self.branch}\n", ""
        if "rev-parse" in args and any("short" in a for a in args):
            return 0, f"{self.sha}\n", ""
        return 1, "", "err"


class TestMatchChannelForBranch(unittest.TestCase):
    def test_main_maps_to_stable(self) -> None:
        info = match_channel_for_branch(ReleaseChannelRegistry(), "main")
        self.assertEqual(info["active_channel_id"], "stable")

    def test_rc_branch_maps_to_rc_channel(self) -> None:
        info = match_channel_for_branch(ReleaseChannelRegistry(), "feat/v0.7.4")
        self.assertEqual(info["active_channel_id"], "rc-074")

    def test_unknown_branch_maps_to_custom(self) -> None:
        info = match_channel_for_branch(ReleaseChannelRegistry(), "feat/other")
        self.assertEqual(info["active_channel_id"], "custom")
        self.assertIn("feat/other", info["active_channel_label"])


class TestReadInstallGitRef(unittest.TestCase):
    def test_reads_branch_and_sha(self) -> None:
        runner = _FakeGitRunner(branch="feat/v0.7.4", sha="deadbeef")
        branch, sha = read_install_git_ref(
            "/opt/meshpoint", runner=runner, use_sudo=False,
        )
        self.assertEqual(branch, "feat/v0.7.4")
        self.assertEqual(sha, "deadbeef")


class TestBuildInstallStatusPayload(unittest.TestCase):
    def test_null_branch_does_not_default_to_stable(self) -> None:
        runner = _FakeGitRunner(branch="", sha="")
        runner.__call__ = lambda args, cwd, timeout: (1, "", "denied")  # noqa: E731
        with mock.patch(
            "src.api.update.install_status.fetch_remote_version_sync",
            return_value=None,
        ):
            payload = build_install_status_payload(
                registry=ReleaseChannelRegistry(),
                repo_path="/opt/meshpoint",
                runner=runner,
                use_sudo=False,
            )
        self.assertIsNone(payload["install_branch"])
        self.assertIsNone(payload["active_channel_id"])

    def test_payload_includes_branch_and_channel(self) -> None:
        runner = _FakeGitRunner()
        with mock.patch(
            "src.api.update.install_status.fetch_remote_version_sync",
            return_value="0.7.3.1",
        ):
            with mock.patch(
                "src.api.update.install_status.__version__",
                "0.7.3.1",
            ):
                payload = build_install_status_payload(
                    registry=ReleaseChannelRegistry(),
                    repo_path="/opt/meshpoint",
                    runner=runner,
                    use_sudo=False,
                )
        self.assertEqual(payload["install_branch"], "feat/v0.7.4")
        self.assertEqual(payload["active_channel_id"], "rc-074")
        self.assertEqual(payload["remote_branch"], "feat/v0.7.4")
        self.assertFalse(payload["update_available"])


if __name__ == "__main__":
    unittest.main()
