"""Private-pipe Reticulum worker. No externally reachable HTTP listener."""
import asyncio
import base64
from contextvars import ContextVar
import json
import logging
from pathlib import Path
import sys
from types import SimpleNamespace
from fastapi import FastAPI
from src.api.auth.dependencies import require_admin, require_auth
from src.api.auth.jwt_session import SessionClaims
from src.api.audit import AuditLogWriter
from src.api.audit.dependencies import get_audit_writer
from src.config import AppConfig
from src.plugins.manifest import parse_manifest
from src.plugins.runtime import Registration
from backend import service_builder

PREFIX = "MESHPOINT_RPC "
MAX_BODY = 2 * 1024 * 1024
subject = ContextVar("subject", default="plugin")


def emit(message):
    print(PREFIX + json.dumps(message), flush=True)


class Events:
    async def broadcast(self, event_type, data):
        if event_type.startswith("reticulum_"):
            emit({"event": event_type, "data": data})


async def dispatch(app, message):
    body = base64.b64decode(message.get("body", ""))
    content_type = message.get("content_type", "")
    scope = {"type": "http", "asgi": {"version": "3.0", "spec_version": "2.4"},
             "http_version": "1.1", "method": message["method"], "scheme": "http",
             "path": message["path"], "raw_path": message["path"].encode(), "root_path": "",
             "query_string": message.get("query", "").encode(),
             "headers": [(b"content-type", content_type.encode()), (b"content-length", str(len(body)).encode())],
             "client": ("local", 0), "server": ("reticulum", 0)}
    result = {"id": message["id"], "status": 500, "headers": []}
    output = bytearray()

    async def receive():
        return {"type": "http.request", "body": body, "more_body": False}

    async def send(event):
        if event["type"] == "http.response.start":
            result["status"] = event["status"]
            result["headers"] = [(k.decode("latin-1"), v.decode("latin-1")) for k, v in event.get("headers", [])]
        elif event["type"] == "http.response.body":
            output.extend(event.get("body", b""))
            if len(output) > MAX_BODY:
                raise ValueError("Response too large")

    token = subject.set(message.get("subject", "plugin"))
    try:
        await app(scope, receive, send)
        result["body"] = base64.b64encode(output).decode()
    except Exception:
        result.update(status=500, headers=[("content-type", "application/json")],
                      body=base64.b64encode(b'{"detail":"Reticulum request failed"}').decode())
    finally:
        subject.reset(token)
    emit(result)


async def main():
    logging.basicConfig(level=logging.WARNING, stream=sys.stderr)
    bootstrap = json.loads(sys.stdin.readline())
    config = AppConfig()
    config.radio.region = bootstrap.get("radio_region", "UNKNOWN")
    config.storage.database_path = bootstrap["database_path"]
    for key in ("hardware_description", "latitude", "longitude"):
        if key in bootstrap.get("device", {}):
            setattr(config.device, key, bootstrap["device"][key])
    root = Path(__file__).resolve().parent
    reg = Registration(parse_manifest(root), bootstrap["settings"])
    service_builder.register(reg)
    context = SimpleNamespace(config=config, ws_manager=Events(), pipeline=None)
    _, build, wire = reg.services[0]
    service = build(context)
    wire(service, context)
    app = FastAPI()
    for router in reg.routers:
        app.include_router(router)
    # These dependencies are satisfied only for requests received over this
    # private parent-owned pipe, after the parent has checked admin auth.
    def claims():
        return SessionClaims(subject.get(), "admin", 1)
    app.dependency_overrides[require_admin] = claims
    app.dependency_overrides[require_auth] = claims
    audit = AuditLogWriter(service.base / "audit.jsonl")
    app.dependency_overrides[get_audit_writer] = lambda: audit
    tasks = set()
    try:
        await service.start()
        emit({"ready": True, "daemon_pid": service.daemon.pid})
        while line := await asyncio.to_thread(sys.stdin.readline):
            message = json.loads(line)
            if message.get("op") == "shutdown":
                break
            if len(tasks) >= 16:
                emit({"id": message["id"], "status": 429, "body": "", "headers": []})
                continue
            task = asyncio.create_task(dispatch(app, message))
            tasks.add(task)
            task.add_done_callback(tasks.discard)
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await service.stop()


if __name__ == "__main__":
    asyncio.run(main())
