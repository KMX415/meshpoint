"""App-scoped optional plugin lifecycle using javastraat's manifest contract.

Registration is staged until a plugin succeeds. No global registries leak
between app instances; failed plugins cannot leave partially mounted routes.
"""
from __future__ import annotations

import asyncio
import importlib.util
import logging
import sys
import subprocess
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

from fastapi import APIRouter, Depends
from src.api.auth.dependencies import require_auth
from src.plugins.manifest import PluginManifest, parse_manifest
from src.plugins.dependencies import dependency_report

logger = logging.getLogger(__name__)
SUPPORTED_CAPABILITIES = frozenset({"routes", "service", "sidebar", "hook", "listener", "topbar"})


class Registration:
    def __init__(self, manifest: PluginManifest, config: dict):
        self.manifest = manifest
        self.name = manifest.name
        self.config = dict(config)
        self.routers = []
        self.services = []
        self.listeners = []

    def add_listener(self, name, build, wire=None):
        """Register an idle receiver. build must not start or open hardware.

        The reviewed ACARS constructor only initializes buffers and locks;
        its separate admin-only /start endpoint claims and opens the SDR.
        """
        if "listener" not in self.manifest.provides or not callable(build):
            raise ValueError("Plugin listener must be declared with a callable builder")
        self.listeners.append((name, build, wire))

    def add_router(self, router, *, public=False):
        if "routes" not in self.manifest.provides or public:
            raise ValueError("Plugin routes must be declared and authenticated")
        if not isinstance(router, APIRouter):
            raise ValueError("Plugin must register an APIRouter")
        self.routers.append(router)

    def add_service(self, name, build, wire=None):
        if "service" not in self.manifest.provides or not callable(build):
            raise ValueError("Plugin service must be declared with a callable builder")
        self.services.append((name, build, wire))


@dataclass
class PluginState:
    name: str
    manifest: PluginManifest | None = None
    status: str = "installed"
    error: str = ""
    registration: Registration | None = None


class PluginRuntime:
    def __init__(self, apps_dir: Path, config):
        self.apps_dir = apps_dir
        self.config = config
        self.states = {}
        self.live = []
        self.mutation_lock = asyncio.Lock()

    def discover(self):
        if not self.apps_dir.is_dir():
            return
        for folder in sorted(self.apps_dir.iterdir()):
            if not folder.is_dir() or folder.is_symlink():
                continue
            if folder.name in self.states:
                continue
            state = PluginState(folder.name)
            self.states[folder.name] = state
            try:
                state.manifest = parse_manifest(folder)
                unsupported = set(state.manifest.provides) - SUPPORTED_CAPABILITIES
                if unsupported:
                    state.status = "incompatible"
                    state.error = "Capabilities not yet integrated: " + ", ".join(sorted(unsupported))
            except Exception as exc:
                state.status = "failed"
                state.error = "Invalid plugin manifest: " + type(exc).__name__
                logger.warning("Invalid plugin manifest: %s", folder.name)

    def mount(self, app):
        occupied = {(r.path, method) for r in app.routes for method in getattr(r, "methods", ())}
        for state in self.states.values():
            conf = self.config.plugins.get(state.name, {})
            if state.status != "installed" or conf.get("enabled") is not True:
                continue
            manifest = state.manifest
            if state.name == "reticulum":
                from src.plugins.python_dependencies import is_ready
                if not is_ready(self.apps_dir):
                    state.status = "setup needed"
                    continue
            if not dependency_report(manifest)["ready"]:
                state.status = "setup needed"
                continue
            if manifest.setup and not manifest.check:
                state.status = "setup needed"
                continue
            if manifest.check:
                try:
                    probe = subprocess.run(
                        ["bash", str(manifest.check_path)], cwd=manifest.path,
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                        timeout=15, check=False,
                    )
                    if probe.returncode:
                        state.status = "setup needed"
                        continue
                except (OSError, subprocess.TimeoutExpired):
                    state.status = "setup needed"
                    continue
            module_name = f"meshpoint_plugin_{state.name.replace('-', '_')}_{id(self)}"
            try:
                backend = manifest.path / "backend" / "__init__.py"
                if manifest.path.resolve() not in backend.resolve().parents:
                    raise ValueError("Plugin backend escapes its directory")
                spec = importlib.util.spec_from_file_location(
                    module_name, backend, submodule_search_locations=[str(backend.parent)],
                )
                module = importlib.util.module_from_spec(spec)
                sys.modules[module_name] = module
                spec.loader.exec_module(module)
                registration = Registration(manifest, conf)
                registration.radio_region = self.config.radio.region
                module.register(registration)
                staged = APIRouter()
                staged_keys = set()
                for router in registration.routers:
                    for route in router.routes:
                        if not route.path.startswith('/api/') or not getattr(route, 'methods', None):
                            raise ValueError("Only authenticated HTTP API routes are supported")
                        for method in route.methods:
                            key = (route.path, method)
                            if key in occupied or key in staged_keys:
                                raise ValueError("Plugin route conflicts with an existing route")
                            staged_keys.add(key)
                    staged.include_router(router, dependencies=[Depends(require_auth)])
                app.include_router(staged)
                occupied.update(staged_keys)
                state.registration = registration
                state.status = "loaded"
            except Exception as exc:
                state.status = "failed"
                state.error = "Plugin registration failed: " + type(exc).__name__
                for key in list(sys.modules):
                    if key == module_name or key.startswith(module_name + '.'):
                        sys.modules.pop(key, None)
                logger.warning("Plugin %s failed to register (%s)", state.name, type(exc).__name__)

    async def start(self, pipeline, ws_manager):
        context = SimpleNamespace(pipeline=pipeline, ws_manager=ws_manager, config=self.config,
                                  plugin_lock=self.mutation_lock)
        for state in self.states.values():
            if state.registration is None:
                continue
            for name, build, wire in state.registration.listeners:
                obj = None
                try:
                    obj = build()
                    if wire:
                        wire(obj)
                    for listener in obj if isinstance(obj, tuple) else (obj,):
                        self.live.append((state.name, listener))
                except Exception as exc:
                    state.status = "failed"
                    state.error = "Plugin listener failed: " + type(exc).__name__
                    for listener in obj if isinstance(obj, tuple) else (obj,):
                        if listener is not None:
                            await self._stop(listener)
                    logger.warning("Plugin listener %s failed (%s)", name, type(exc).__name__)
            for name, build, wire in state.registration.services:
                service = None
                try:
                    service = build(context)
                    if service is None:
                        continue
                    if wire:
                        wire(service, context)
                    await asyncio.wait_for(service.start(), timeout=30)
                    self.live.append((state.name, service))
                except Exception as exc:
                    state.status = "failed"
                    state.error = "Plugin service failed: " + type(exc).__name__
                    if service is not None:
                        await self._stop(service)
                    logger.warning("Plugin service %s failed (%s)", name, type(exc).__name__)

    async def _stop(self, service):
        try:
            await asyncio.wait_for(service.stop(), timeout=10)
        except Exception:
            logger.warning("Plugin service cleanup failed")

    async def stop(self):
        for _, service in reversed(self.live):
            await self._stop(service)
        self.live.clear()
