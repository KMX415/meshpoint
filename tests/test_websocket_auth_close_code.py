"""Regression tests for the v0.7.3.1 WS auth-close-code bug.

In v0.7.3, ``server.py`` called ``await websocket.close(code=4401)``
*before* ``await websocket.accept()``. Starlette translates that into
an HTTP 403 on the WebSocket upgrade, which browsers report to JS as
close code ``1006`` (Abnormal Closure) instead of the negotiated
``4401``. The dashboard's WS client only redirects to ``/login`` on
``4401``; everything else falls through to the reconnect loop, so
unauthenticated users were stranded indefinitely on "Reconnecting..."
after upgrading.

The fix moved the auth-rejection logic into ``_gate_ws_or_close``
which always ``accept()``s before ``close()``. These tests pin the
call order at the production-endpoint level so a future refactor
cannot silently re-introduce the bug. ``starlette.testclient`` masks
the difference between pre- and post-accept close (both surface as
``WebSocketDisconnect`` with the right code), which is precisely why
the v0.7.3 CI suite failed to catch this.
"""

from __future__ import annotations

import unittest
from typing import Optional
from unittest.mock import AsyncMock

from src.api.auth.jwt_session import ROLE_ADMIN, JwtSessionService
from src.api.auth.ws_guard import WS_AUTH_CLOSE_CODE
from src.api.server import _gate_ws_or_close

_SECRET = "ws-close-code-test-secret-" + "x" * 16


def _service() -> JwtSessionService:
    return JwtSessionService(secret=_SECRET, expiry_minutes=60, session_version=1)


class _FakeWebSocket:
    """Minimal WebSocket stand-in that records call order."""

    def __init__(self, cookie_token: Optional[str] = None) -> None:
        self.cookies = {"meshpoint_session": cookie_token} if cookie_token else {}
        self.query_params = {}
        self.calls: list[str] = []
        self.accept = AsyncMock(side_effect=self._record_accept)
        self.close = AsyncMock(side_effect=self._record_close)

    async def _record_accept(self, *_args, **_kwargs) -> None:
        self.calls.append("accept")

    async def _record_close(self, *_args, **kwargs) -> None:
        self.calls.append(f"close:{kwargs.get('code')}")


class TestGateWsOrCloseRejectionPath(unittest.IsolatedAsyncioTestCase):
    async def test_no_token_calls_accept_before_close(self) -> None:
        ws = _FakeWebSocket()
        ok = await _gate_ws_or_close(ws, _service())

        self.assertFalse(ok)
        self.assertEqual(ws.calls, ["accept", f"close:{WS_AUTH_CLOSE_CODE}"])
        ws.accept.assert_awaited_once()
        ws.close.assert_awaited_once_with(code=WS_AUTH_CLOSE_CODE)

    async def test_invalid_token_calls_accept_before_close(self) -> None:
        ws = _FakeWebSocket(cookie_token="not-a-jwt")
        ok = await _gate_ws_or_close(ws, _service())

        self.assertFalse(ok)
        self.assertEqual(ws.calls, ["accept", f"close:{WS_AUTH_CLOSE_CODE}"])

    async def test_close_uses_negotiated_4401_code(self) -> None:
        ws = _FakeWebSocket()
        await _gate_ws_or_close(ws, _service())
        ws.close.assert_awaited_once_with(code=4401)

    async def test_jwt_service_none_treated_as_unauth(self) -> None:
        ws = _FakeWebSocket()
        ok = await _gate_ws_or_close(ws, None)
        self.assertFalse(ok)
        self.assertEqual(ws.calls, ["accept", f"close:{WS_AUTH_CLOSE_CODE}"])


class TestGateWsOrCloseAuthorizedPath(unittest.IsolatedAsyncioTestCase):
    async def test_valid_cookie_returns_true_without_calling_close(self) -> None:
        service = _service()
        token = service.issue("admin", ROLE_ADMIN)
        ws = _FakeWebSocket(cookie_token=token)

        ok = await _gate_ws_or_close(ws, service)

        self.assertTrue(ok)
        self.assertEqual(ws.calls, [])
        ws.accept.assert_not_awaited()
        ws.close.assert_not_awaited()


class TestGateWsCallOrderIsExplicit(unittest.IsolatedAsyncioTestCase):
    """Defense against the specific regression: accept must precede close."""

    async def test_accept_index_strictly_lower_than_close_index(self) -> None:
        ws = _FakeWebSocket()
        await _gate_ws_or_close(ws, _service())

        accept_idx = ws.calls.index("accept")
        close_idx = ws.calls.index(f"close:{WS_AUTH_CLOSE_CODE}")
        self.assertLess(
            accept_idx,
            close_idx,
            "accept() must be awaited before close() so the custom "
            "close code reaches the browser; pre-accept close causes "
            "Starlette to send HTTP 403 and the close code is lost.",
        )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
