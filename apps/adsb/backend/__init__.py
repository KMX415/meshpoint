"""ADS-B plugin -- entry point.

Meshpoint's plugin loader imports this module and calls ``register(reg)``
when ``plugins.adsb.enabled: true`` is set in config. See
``plugins/apps/adsb/plugin.toml`` and ``docs/CONFIGURATION.md`` (Plugins).

Imports are deferred into ``register()`` so ``backend.listener`` (stdlib
only) can be imported for its own tests without pulling in FastAPI.
"""

from __future__ import annotations


def register(reg) -> None:
    from .listener import AdsbListener
    from .routes import init_routes, router

    reg.add_router(router)
    reg.add_listener("adsb", AdsbListener, init_routes)
