from __future__ import annotations


def register(reg) -> None:
    from .listener import RtlListener
    from .routes import init_routes, router

    reg.add_router(router)
    reg.add_listener("radio", lambda: RtlListener(region=getattr(reg, "radio_region", "UNKNOWN"), deemphasis_us=reg.config.get("deemphasis_us")), init_routes)
