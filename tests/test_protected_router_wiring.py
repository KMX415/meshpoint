"""Integration tests for the include-time auth contract.

Mirrors the wiring that ``src.api.server.create_app`` uses:

- public routers mounted with no auth dependency
- protected routers mounted with ``dependencies=[Depends(require_auth)]``
- WS handshake gated by ``authenticate_websocket``

Confirms that a router mounted with ``Depends(require_auth)`` rejects
anonymous requests with 401 across every method on it, accepts a
valid session cookie, and that the WS guard rejects un-authed
upgrades with the negotiated 4401 close code.
"""

from __future__ import annotations

import unittest

from fastapi import APIRouter, Depends, FastAPI, WebSocket, WebSocketDisconnect
from fastapi.testclient import TestClient

from src.api.auth import dependencies as auth_deps
from src.api.auth.dependencies import SESSION_COOKIE_NAME, require_auth
from src.api.auth.jwt_session import ROLE_ADMIN, JwtSessionService
from src.api.auth.ws_guard import WS_AUTH_CLOSE_CODE, authenticate_websocket

_SECRET = "wiring-test-secret-" + "q" * 16


def _build_protected_router() -> APIRouter:
    router = APIRouter(prefix="/api/sample", tags=["sample"])

    @router.get("/ping")
    def ping():
        return {"pong": True}

    @router.post("/echo")
    def echo():
        return {"echoed": True}

    return router


def _build_app(jwt_service: JwtSessionService) -> FastAPI:
    app = FastAPI()
    app.include_router(
        _build_protected_router(),
        dependencies=[Depends(require_auth)],
    )

    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket):
        claims = authenticate_websocket(websocket, jwt_service)
        if claims is None:
            await websocket.close(code=WS_AUTH_CLOSE_CODE)
            return
        await websocket.accept()
        try:
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            return

    return app


class TestProtectedRouterWiring(unittest.TestCase):
    def setUp(self) -> None:
        self.service = JwtSessionService(
            secret=_SECRET, expiry_minutes=60, session_version=1
        )
        auth_deps.init_auth(self.service)
        self.client = TestClient(_build_app(self.service))

    def tearDown(self) -> None:
        auth_deps.reset_auth()

    def test_get_on_protected_router_without_auth_is_401(self) -> None:
        response = self.client.get("/api/sample/ping")
        self.assertEqual(response.status_code, 401)

    def test_post_on_protected_router_without_auth_is_401(self) -> None:
        response = self.client.post("/api/sample/echo")
        self.assertEqual(response.status_code, 401)

    def test_protected_router_accepts_valid_cookie(self) -> None:
        token = self.service.issue("admin", ROLE_ADMIN)
        self.client.cookies.set(SESSION_COOKIE_NAME, token)
        response = self.client.get("/api/sample/ping")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"pong": True})

    def test_protected_router_accepts_bearer_header(self) -> None:
        token = self.service.issue("admin", ROLE_ADMIN)
        response = self.client.get(
            "/api/sample/ping",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(response.status_code, 200)


class TestWebsocketAuthGate(unittest.TestCase):
    def setUp(self) -> None:
        self.service = JwtSessionService(
            secret=_SECRET, expiry_minutes=60, session_version=1
        )
        auth_deps.init_auth(self.service)
        self.client = TestClient(_build_app(self.service))

    def tearDown(self) -> None:
        auth_deps.reset_auth()

    def test_ws_rejects_anonymous_with_4401(self) -> None:
        with self.assertRaises(WebSocketDisconnect) as ctx:
            with self.client.websocket_connect("/ws"):
                pass
        self.assertEqual(ctx.exception.code, WS_AUTH_CLOSE_CODE)

    def test_ws_accepts_valid_cookie(self) -> None:
        token = self.service.issue("admin", ROLE_ADMIN)
        self.client.cookies.set(SESSION_COOKIE_NAME, token)
        with self.client.websocket_connect("/ws") as ws:
            ws.close()

    def test_ws_accepts_query_token_fallback(self) -> None:
        token = self.service.issue("admin", ROLE_ADMIN)
        with self.client.websocket_connect(f"/ws?token={token}") as ws:
            ws.close()

    def test_ws_rejects_invalid_token(self) -> None:
        with self.assertRaises(WebSocketDisconnect) as ctx:
            with self.client.websocket_connect("/ws?token=not-a-jwt"):
                pass
        self.assertEqual(ctx.exception.code, WS_AUTH_CLOSE_CODE)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
