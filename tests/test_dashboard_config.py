"""Dashboard metadata available to signed-in viewers and administrators."""
import unittest
from types import SimpleNamespace
from src.api.routes import config_routes
from src.config import AppConfig


class TestDashboardConfig(unittest.IsolatedAsyncioTestCase):
    async def test_capture_sources_are_available_for_topbar_visibility(self):
        previous = config_routes._config
        config = AppConfig()
        config.capture.sources = ["serial", "meshcore_usb"]
        config_routes._config = config
        try:
            for role in ["admin", "viewer"]:
                payload = await config_routes.get_config(SimpleNamespace(role=role))
                self.assertEqual(payload["capture"]["sources"], ["serial", "meshcore_usb"])
        finally:
            config_routes._config = previous
