"""P2000 plugin -- entry point.

Meshpoint's plugin loader imports this module and calls ``register(reg)``
when ``plugins.p2000.enabled: true`` is set in config. See
``plugins/apps/p2000/plugin.toml`` and ``docs/CONFIGURATION.md`` (Plugins).

Imports are deferred into ``register()`` so ``backend.listener`` (stdlib
only) can be imported for its own tests without pulling in FastAPI.
"""

from __future__ import annotations


def register(reg) -> None:
    from .listener import P2000Listener
    from .routes import init_routes, router

    reg.add_router(router)
    reg.add_listener("p2000", P2000Listener, init_routes)
