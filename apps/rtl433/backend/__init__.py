"""RTL433 plugin -- entry point.

Meshpoint's plugin loader imports this module and calls ``register(reg)``
when ``plugins.rtl433.enabled: true`` is set in config. See
``plugins/apps/rtl433/plugin.toml`` and ``docs/CONFIGURATION.md`` (Plugins).

Imports are deferred into ``register()`` so ``backend.listener`` (stdlib
only) can be imported for its own tests without pulling in FastAPI.
"""

from __future__ import annotations


def register(reg) -> None:
    from .listener import Rtl433Listener
    from .routes import init_routes, router

    reg.add_router(router)
    reg.add_listener("rtl433", lambda: Rtl433Listener(frequency_mhz=reg.config.get("frequency_mhz")), init_routes)
