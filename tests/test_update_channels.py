"""Tests for the release-channel registry."""

from __future__ import annotations

import unittest

from src.api.update.channels import (
    DEFAULT_CHANNELS,
    ReleaseChannel,
    ReleaseChannelRegistry,
    TIER_CUSTOM,
)


class TestReleaseChannelRegistry(unittest.TestCase):
    def test_default_channels_have_unique_ids(self) -> None:
        ids = [c.id for c in DEFAULT_CHANNELS]
        self.assertEqual(len(ids), len(set(ids)))

    def test_to_payload_serializes_each_channel(self) -> None:
        payload = ReleaseChannelRegistry().to_payload()
        self.assertEqual(len(payload), len(DEFAULT_CHANNELS))
        for entry in payload:
            self.assertIn("id", entry)
            self.assertIn("branch", entry)
            self.assertIn("tier", entry)

    def test_resolve_branch_for_known_stable(self) -> None:
        registry = ReleaseChannelRegistry()
        self.assertEqual(registry.resolve_branch("stable"), "main")

    def test_resolve_branch_for_unknown_returns_none(self) -> None:
        self.assertIsNone(ReleaseChannelRegistry().resolve_branch("nope"))

    def test_resolve_branch_for_custom_requires_safe_name(self) -> None:
        registry = ReleaseChannelRegistry()
        self.assertEqual(
            registry.resolve_branch("custom", custom_branch="feat/foo"),
            "feat/foo",
        )

    def test_resolve_branch_rejects_shell_metachars(self) -> None:
        registry = ReleaseChannelRegistry()
        for evil in ("foo;rm", "foo bar", "foo|bar", "$(boom)", "-malicious"):
            self.assertIsNone(
                registry.resolve_branch("custom", custom_branch=evil)
            )

    def test_custom_channel_without_branch_returns_none(self) -> None:
        self.assertIsNone(ReleaseChannelRegistry().resolve_branch("custom"))

    def test_find_returns_channel(self) -> None:
        match = ReleaseChannelRegistry().find("rc-074")
        self.assertIsNotNone(match)
        self.assertEqual(match.tier, "rc")


if __name__ == "__main__":
    unittest.main()
