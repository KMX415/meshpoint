"""Optional Reticulum integration, adapted from Einstein PD2EMC's plugin."""
from pathlib import Path


def register(reg):
    from src.storage.database import DatabaseManager
    from src.storage.message_repository import MessageRepository
    from . import config_routes, nomad_routes, routes, state
    from .managed_service import ManagedReticulum
    from .peer_repo import ReticulumPeerRepository

    reg.add_router(routes.router)
    reg.add_router(config_routes.router)
    reg.add_router(nomad_routes.router)

    def build(context):
        base = Path(context.config.storage.database_path).resolve().parent / "reticulum"
        settings = {**reg.config,
                    "reticulum_config_dir": str(base / "rns_config"),
                    "identity_path": str(base / "identity"),
                    "lxmf_storage_dir": str(base / "lxmf"),
                    "node_pages_dir": str(base / "pages")}
        state.init(settings, region=context.config.radio.region)
        db = DatabaseManager(str(base / "messages.db"))
        peers = ReticulumPeerRepository(db)
        messages = MessageRepository(db)
        async def node_stats():
            from src.version import __version__
            from .host_stats import read_host
            known = await peers.list_peers()
            return {"version": __version__, "hardware": context.config.device.hardware_description,
                    "lxmf_peers": await peers.count("lxmf.delivery"),
                    "nomad_nodes": await peers.count("nomadnetwork.node"),
                    "conversations": len(await messages.get_conversations()),
                    "recent_nodes": [p.to_dict() for p in known[:20]], "host": read_host()}
        telemetry = state.telemetry_config()
        if telemetry.get("include_location"):
            dev = context.config.device
            telemetry["location"] = {"latitude": dev.latitude, "longitude": dev.longitude,
                                     "altitude": getattr(dev, "altitude", None)}
        return ManagedReticulum(
            database=db, plugin_dir=reg.manifest.path, base=base,
            display_name=state.display_name(), reticulum_config_dir=state.reticulum_config_dir(),
            identity_path=state.identity_path(), lxmf_storage_dir=state.lxmf_storage_dir(),
            message_repo=messages, peer_repo=peers, ws_manager=context.ws_manager,
            node_stats_provider=node_stats,
            node_cfg=state.node_config(), hardware_description=context.config.device.hardware_description,
            project_url="https://github.com/KMX415/meshpoint",
            spaceapi_url=state.node_config()["spaceapi_url"],
            events_ical_url=state.node_config()["events_ical_url"], notify_url=state.notify_url(),
            propagation_cfg=state.propagation_config(),
            talkback_enabled=state.node_config()["talkback_enabled"], telemetry_cfg=telemetry,
        )

    def wire(service, context):
        routes.init_routes(service, service._message_repo)
        nomad_routes.init_routes(service)

    reg.add_service("reticulum", build, wire)
