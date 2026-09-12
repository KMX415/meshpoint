"""Reticulum runs in its own process so daemon failures cannot exit Meshpoint."""

def register(reg):
    from .worker_proxy import ReticulumWorker, build_router
    holder = {}
    reg.add_router(build_router(holder))
    def build(context):
        return ReticulumWorker(reg.manifest.path, reg.config, context)
    def wire(service, context):
        holder["service"] = service
    reg.add_service("reticulum-worker", build, wire)
