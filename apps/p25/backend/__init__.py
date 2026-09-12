def register(reg):
    from .listener import P25Listener
    from .routes import init_routes, router
    reg.add_router(router)
    reg.add_listener("p25", P25Listener, init_routes)
