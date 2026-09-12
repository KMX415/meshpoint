"""Catalog packages must register and remain idle without native dependencies."""
import json
import unittest
from pathlib import Path
from unittest.mock import patch
from fastapi import FastAPI
from src.config import AppConfig
from src.plugins.runtime import PluginRuntime
from src.plugins.sources import parse_catalog
from src.plugins.manifest import parse_manifest
from src.audio import sdr_registry

ROOT = Path(__file__).resolve().parents[1]


class TestOptionalReceivers(unittest.IsolatedAsyncioTestCase):
    async def test_catalog_matches_payloads(self):
        catalog = parse_catalog((ROOT / "repo.json").read_bytes())
        for entry in catalog["plugins"]:
            manifest = parse_manifest(ROOT / entry["path"])
            self.assertEqual(manifest.name, entry["id"])
            self.assertEqual(manifest.version, entry["version"])
            self.assertEqual(list(manifest.provides), entry["provides"])
            self.assertFalse(manifest.locked)
            self.assertIsNone(manifest.setup)
            self.assertIsNone(manifest.check)

    async def test_enabled_receivers_register_without_opening_hardware(self):
        config = AppConfig()
        catalog = json.loads((ROOT / "repo.json").read_text(encoding="utf-8"))
        config.plugins = {entry["id"]: {"enabled": True} for entry in catalog["plugins"] if entry["id"] != "reticulum"}
        runtime = PluginRuntime(ROOT / "apps", config)
        runtime.discover()
        with patch("src.plugins.dependencies.shutil.which", return_value="native-tool"), \
             patch("asyncio.create_subprocess_exec", side_effect=AssertionError("hardware opened")), \
             patch("asyncio.create_subprocess_shell", side_effect=AssertionError("hardware opened")):
            runtime.mount(FastAPI())
            await runtime.start(None, None)
            try:
                for name, state in runtime.states.items():
                    if name not in config.plugins:
                        continue
                    self.assertEqual(state.status, "loaded", (name, state.error))
                self.assertIsNone(sdr_registry.current_owner())
            finally:
                await runtime.stop()
        self.assertIsNone(sdr_registry.current_owner())

    async def test_missing_native_tools_leave_plugins_unloaded(self):
        config = AppConfig()
        config.plugins["acars"] = {"enabled": True}
        runtime = PluginRuntime(ROOT / "apps", config)
        runtime.discover()
        with patch("src.plugins.dependencies.shutil.which", return_value=None):
            runtime.mount(FastAPI())
        self.assertEqual(runtime.states["acars"].status, "setup needed")
        self.assertIsNone(runtime.states["acars"].registration)
