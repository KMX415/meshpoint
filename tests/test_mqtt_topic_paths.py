"""Tests for MQTT topic prefix composition."""

from __future__ import annotations

import unittest

from src.relay.mqtt_formatter import _build_topic_prefix


class TestMqttTopicPrefix(unittest.TestCase):
    def test_default_root_and_region(self):
        self.assertEqual(_build_topic_prefix("msh", "US"), "msh/US")

    def test_hierarchical_region_path(self):
        self.assertEqual(_build_topic_prefix("msh", "US/FL"), "msh/US/FL")

    def test_topic_root_can_include_region_segments(self):
        self.assertEqual(_build_topic_prefix("msh/US", "FL"), "msh/US/FL")

    def test_prevents_duplicate_region_suffix(self):
        self.assertEqual(_build_topic_prefix("msh/US", "US"), "msh/US")

    def test_strips_slashes(self):
        self.assertEqual(_build_topic_prefix("/msh/US/", "/FL/"), "msh/US/FL")


if __name__ == "__main__":
    unittest.main()
