"""Node platform PUT guards on config routes."""

import unittest

from fastapi import HTTPException

from src.api.routes import config_routes
from src.config import AppConfig, DeviceConfig, TransmitConfig


class TestConfigNodeGuards(unittest.TestCase):
    def setUp(self):
        config_routes._config = AppConfig()
        config_routes._config.device = DeviceConfig(platform="node")
        config_routes._config.transmit = TransmitConfig()
        config_routes._tx_service = None
        config_routes._identity = None
        config_routes._bridge_status_provider = None

    def tearDown(self):
        config_routes._config = None

    def test_transmit_put_returns_409_on_node(self):
        import asyncio
        from src.api.routes.config_routes import TransmitUpdate, update_transmit

        with self.assertRaises(HTTPException) as ctx:
            asyncio.run(update_transmit(TransmitUpdate(enabled=True)))
        self.assertEqual(ctx.exception.status_code, 409)

    def test_radio_put_returns_409_on_node(self):
        import asyncio
        from src.api.routes.config_routes import RadioUpdate, update_radio

        with self.assertRaises(HTTPException) as ctx:
            asyncio.run(update_radio(RadioUpdate(region="US")))
        self.assertEqual(ctx.exception.status_code, 409)


if __name__ == "__main__":
    unittest.main()
