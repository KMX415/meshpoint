"""POCSAG plugin -- entry point.

Meshpoint's plugin loader imports this module and calls ``register(reg)``
when ``plugins.pocsag.enabled: true`` is set in config. See
``plugins/apps/pocsag/plugin.toml`` and ``docs/CONFIGURATION.md`` (Plugins).

Imports are deferred into ``register()`` so ``backend.listener`` (stdlib
only) can be imported for its own tests without pulling in FastAPI.
"""

from __future__ import annotations


def register(reg) -> None:
    from .listener import PocsagListener
    from .routes import init_routes, router

    reg.add_router(router)
    reg.add_listener("pocsag", lambda: PocsagListener(frequency_mhz=reg.config.get("frequency_mhz")), init_routes)
