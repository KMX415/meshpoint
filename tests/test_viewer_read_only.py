"""Viewer reads must never mutate shared state, even when bypassing the UI."""

from unittest.mock import AsyncMock

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from src.api.auth import dependencies
from src.api.auth.jwt_session import JwtSessionService
from src.api.routes import messages


@pytest.fixture
def clients(monkeypatch):
    jwt = JwtSessionService(
        "viewer-boundary-test-" + "x" * 32, expiry_minutes=60, session_version=1,
    )
    dependencies.init_auth(jwt)
    app = FastAPI()
    writes = []

    @app.api_route("/shared", methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
                   dependencies=[Depends(dependencies.require_auth)])
    async def shared():
        writes.append("called")
        return {"ok": True}

    repository = AsyncMock()
    repository.get_conversation.return_value = []
    monkeypatch.setattr(messages, "_message_repo", repository)
    app.include_router(messages.router, dependencies=[Depends(dependencies.require_auth)])
    viewer, admin, anonymous = (TestClient(app) for _ in range(3))
    viewer.headers["Authorization"] = f"Bearer {jwt.issue('viewer', 'viewer')}"
    admin.headers["Authorization"] = f"Bearer {jwt.issue('admin', 'admin')}"
    yield viewer, admin, anonymous, writes, repository
    dependencies.reset_auth()


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
def test_shared_writes_blocked_before_handler(clients, method):
    viewer, admin, anonymous, writes, _ = clients
    assert viewer.request(method, "/shared").status_code == 403
    assert anonymous.request(method, "/shared").status_code == 401
    assert writes == []
    assert admin.request(method, "/shared").status_code == 200
    assert writes == ["called"]


def test_viewer_can_read_without_marking_read(clients):
    viewer, _, _, _, repository = clients
    assert viewer.get("/api/messages/conversation/test-node").status_code == 200
    repository.get_conversation.assert_awaited_once()
    repository.mark_read.assert_not_awaited()


def test_read_marker_requires_admin(clients):
    viewer, admin, anonymous, _, repository = clients
    path = "/api/messages/conversation/test-node/read"
    assert viewer.post(path).status_code == 403
    assert anonymous.post(path).status_code == 401
    repository.mark_read.assert_not_awaited()
    assert admin.post(path).status_code == 200
    repository.mark_read.assert_awaited_once_with("test-node")


@pytest.mark.parametrize("path", ["/api/messages/conversation/test-node", "/api/messages/all"])
def test_viewer_cannot_delete(clients, path):
    viewer, _, _, _, repository = clients
    assert viewer.delete(path).status_code == 403
    repository.delete_conversation.assert_not_awaited()
    repository.delete_all.assert_not_awaited()


def test_all_dashboard_write_routes_have_guard(tmp_path):
    """Check production router wiring, including newly mounted plugin managers."""
    from fastapi import routing
    from src.api.server import create_app
    from src.config import AppConfig

    config = AppConfig()
    config.storage.database_path = str(tmp_path / "test.db")
    config.web_auth.jwt_secret = "route-audit-test-" + "x" * 32
    config.web_auth.admin_password_hash = "test-setup-complete"
    app = create_app(config)

    def guards(dependency):
        found = {dependency.call}
        for child in dependency.dependencies:
            found.update(guards(child))
        return found

    session_routes = {
        "/api/auth/setup", "/api/auth/login", "/api/auth/logout",
        "/api/auth/change_password",
    }
    checked = 0
    # Newer FastAPI retains included routers instead of flattening app.routes.
    # Effective contexts include guards inherited at each include_router call.
    iter_contexts = getattr(routing, "iter_route_contexts", None)
    routes = iter_contexts(app.routes) if iter_contexts else app.routes
    for route in routes:
        original = getattr(route, "original_route", route)
        if not isinstance(original, routing.APIRoute) or not route.methods & {"POST", "PUT", "PATCH", "DELETE"}:
            continue
        if route.path in session_routes:
            continue
        assert guards(route.dependant) & {
            dependencies.require_admin, dependencies.require_auth,
        }, route.path
        checked += 1
    assert checked > 20
    client = TestClient(app)
    assert client.get("/", follow_redirects=False).status_code == 302
    assert client.get("/api/messages/conversations").status_code == 401
    dependencies.reset_auth()
