"""Authenticated HTTP-to-private-pipe adapter for the Reticulum worker.

The worker has no HTTP listener. Only this parent owns its stdin/stdout pipes;
all external requests pass the normal Meshpoint admin authentication gate.
"""
import asyncio
import base64
import json
import os
from pathlib import Path
import sys
import psutil
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from src.api.auth.dependencies import require_admin
from src.config import _get_local_yaml_path
from src.plugins.python_dependencies import environment_dir

PREFIX = "MESHPOINT_RPC "
MAX_BODY = 2 * 1024 * 1024


class ReticulumWorker:
    def __init__(self, plugin_dir, settings, context):
        self.plugin_dir = Path(plugin_dir)
        self.settings = settings
        self.context = context
        self.process = None
        self.reader = None
        self.pending = {}
        self.sequence = 0
        self.write_lock = asyncio.Lock()
        self.ready = None
        self.daemon_identity = None
        self.daemon_monitor = None
        self.failure = ""

    def _check_port(self, settings):
        if not settings.get("rnode_enabled"):
            return
        selected = str(settings.get("rnode_serial_port") or "").strip()
        if not selected:
            raise ValueError("Select an unused RNode serial port")
        cap = self.context.config.capture
        ports = [cap.serial_port, cap.meshcore_usb.serial_port,
                 *(device.serial_port for device in cap.serial)]
        coordinator = getattr(self.context.pipeline, "capture_coordinator", None)
        # Include auto-detected ports after core capture has started, not just
        # explicit configuration. Resolve by-id aliases before comparing.
        for source in getattr(coordinator, "_sources", []):
            ports.extend(getattr(source, key, None) for key in ("_resolved_port", "_port", "_configured_port"))
            interface = getattr(source, "_interface", None)
            ports.append(getattr(interface, "devPath", None))
            ports.append(getattr(getattr(interface, "stream", None), "name", None))
        wanted = os.path.normcase(str(Path(selected).resolve()))
        if any(os.path.normcase(str(Path(port).resolve())) == wanted for port in ports if isinstance(port, str) and port):
            raise ValueError("This serial port is already assigned to core Meshpoint capture")

    async def start(self):
        self._check_port(self.settings)
        loop = asyncio.get_running_loop()
        self.ready = loop.create_future()
        import src
        root = Path(src.__file__).resolve().parents[1]
        env = {key: os.environ[key] for key in ("PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "LANG")
               if key in os.environ}
        env["PYTHONPATH"] = os.pathsep.join((str(root), str(environment_dir(self.plugin_dir.parent).resolve())))
        env["CONCENTRATOR_CONFIG"] = str(_get_local_yaml_path().resolve())
        self.process = await asyncio.create_subprocess_exec(
            sys.executable, "-u", "-B", str(self.plugin_dir / "worker_runner.py"),
            cwd=root, env=env, stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL, limit=8 * 1024 * 1024,
        )
        self.reader = asyncio.create_task(self._read())
        device = self.context.config.device
        description = {"hardware_description": device.hardware_description}
        if self.settings.get("telemetry_include_location"):
            description.update(latitude=device.latitude, longitude=device.longitude)
        await self._write({"settings": self.settings, "device": description,
                           "radio_region": self.context.config.radio.region,
                           "database_path": self.context.config.storage.database_path})
        await asyncio.wait_for(asyncio.shield(self.ready), timeout=20)

    async def _write(self, message):
        async with self.write_lock:
            self.process.stdin.write((json.dumps(message) + "\n").encode())
            await self.process.stdin.drain()

    async def _read(self):
        try:
            while line := await self.process.stdout.readline():
                text = line.decode("utf-8", errors="replace")
                if not text.startswith(PREFIX):
                    continue
                message = json.loads(text[len(PREFIX):])
                if message.get("ready") and not self.ready.done():
                    pid = message.get("daemon_pid")
                    if pid:
                        try:
                            self.daemon_identity = (pid, psutil.Process(pid).create_time())
                        except psutil.NoSuchProcess:
                            pass
                    self.ready.set_result(True)
                    self.daemon_monitor = asyncio.create_task(self._monitor_daemon())
                elif "event" in message:
                    if message["event"].startswith("reticulum_") and self.context.ws_manager:
                        await self.context.ws_manager.broadcast(message["event"], message.get("data"))
                elif message.get("id") in self.pending:
                    future = self.pending[message["id"]]
                    if not future.done():
                        future.set_result(message)
        except (ValueError, OSError):
            pass
        finally:
            if self.daemon_monitor:
                self.daemon_monitor.cancel()
            self.failure = "Reticulum worker stopped; restart Meshpoint to reconnect"
            failure = RuntimeError("Reticulum worker stopped; restart Meshpoint to reconnect")
            if self.ready is not None and not self.ready.done():
                self.ready.set_exception(failure)
            for future in list(self.pending.values()):
                if not future.done():
                    future.set_exception(failure)
            await asyncio.to_thread(self._cleanup_daemon)

    async def _monitor_daemon(self):
        # Linux RNS clients can keep reconnecting after their daemon exits.
        # Do not leave their API reporting a stale running state indefinitely.
        while self.daemon_identity is not None:
            await asyncio.sleep(1)
            pid, created = self.daemon_identity
            try:
                daemon = psutil.Process(pid)
                alive = daemon.create_time() == created and daemon.is_running() and daemon.status() != psutil.STATUS_ZOMBIE
            except psutil.NoSuchProcess:
                alive = False
            if not alive:
                self.failure = "Reticulum daemon stopped; restart Meshpoint to reconnect"
                if self.process is not None and self.process.returncode is None:
                    self.process.terminate()
                return

    def _cleanup_daemon(self):
        if self.daemon_identity is None:
            return
        pid, created = self.daemon_identity
        try:
            process = psutil.Process(pid)
            if process.create_time() == created:
                process.terminate()
                try:
                    process.wait(timeout=3)
                except psutil.TimeoutExpired:
                    process.kill()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    async def request(self, method, path, query, body, subject, content_type):
        if method == "PUT" and path == "/api/config/reticulum":
            async with self.context.plugin_lock:
                self._check_port(json.loads(body))
                result = await self._request(method, path, query, body, subject, content_type)
                if result["status"] == 200:
                    # Keep manager enable/update operations in sync with settings
                    # normalized and persisted by the isolated plugin process.
                    import yaml
                    path = _get_local_yaml_path()
                    saved = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
                    self.context.config.plugins["reticulum"] = saved.get("plugins", {}).get("reticulum", {})
                return result
        return await self._request(method, path, query, body, subject, content_type)

    async def _request(self, method, path, query, body, subject, content_type):
        if self.failure or self.process is None or self.process.returncode is not None or self.reader.done():
            raise RuntimeError("Reticulum worker is not running")
        self.sequence += 1
        request_id = self.sequence
        future = asyncio.get_running_loop().create_future()
        self.pending[request_id] = future
        try:
            await self._write({"id": request_id, "method": method, "path": path, "query": query,
                               "body": base64.b64encode(body).decode(), "subject": subject,
                               "content_type": content_type})
            return await asyncio.wait_for(future, timeout=125)
        finally:
            self.pending.pop(request_id, None)

    async def stop(self):
        if self.daemon_monitor:
            self.daemon_monitor.cancel()
            await asyncio.gather(self.daemon_monitor, return_exceptions=True)
        if self.process is None:
            return
        if self.process.returncode is None:
            try:
                await self._write({"op": "shutdown"})
                await asyncio.wait_for(self.process.wait(), timeout=7)
            except (OSError, asyncio.TimeoutError):
                if self.process.returncode is None:
                    self.process.kill()
                    await self.process.wait()
        if self.reader:
            await self.reader
        if self.ready is not None and self.ready.done() and not self.ready.cancelled():
            self.ready.exception()
        self.process = None


def build_router(holder):
    router = APIRouter()

    async def forward(request: Request, claims=Depends(require_admin)):
        service = holder.get("service")
        if service is None:
            raise HTTPException(503, "Reticulum is not initialized")
        body = bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body) > MAX_BODY:
                raise HTTPException(413, "Reticulum request is too large")
        try:
            result = await service.request(request.method, request.url.path, request.url.query,
                                           bytes(body), claims.subject, request.headers.get("content-type", ""))
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        except (OSError, RuntimeError, asyncio.TimeoutError) as exc:
            raise HTTPException(503, "Reticulum worker unavailable; core capture remains running") from exc
        headers = {k: v for k, v in result.get("headers", [])
                   if k.lower() in {"content-type", "content-disposition", "cache-control"}}
        return Response(base64.b64decode(result.get("body", "")), status_code=result["status"], headers=headers)

    methods = ["GET", "POST", "PUT", "DELETE"]
    router.add_api_route("/api/reticulum/{tail:path}", forward, methods=methods)
    router.add_api_route("/api/config/reticulum", forward, methods=methods)
    router.add_api_route("/api/config/reticulum/{tail:path}", forward, methods=methods)
    return router
