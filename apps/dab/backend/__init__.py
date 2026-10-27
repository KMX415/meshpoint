from __future__ import annotations


def register(reg) -> None:
    from .listener import DabListener
    from .routes import init_routes, router

    reg.add_router(router)
    reg.add_listener("dab", DabListener, init_routes)
