#!/usr/bin/env python3
"""Optional LAN smoke tests for v0.7.4 API surfaces.

Usage (from dev machine on same network as the Pi):

    set MESHPOINT_BASE=http://192.168.0.141:8080
    set MESHPOINT_USER=admin
    set MESHPOINT_PASSWORD=your-admin-password
    python scripts/smoke_v074_api.py

Exits 0 when all checks pass, 1 otherwise. Skips destructive actions
(clear_database, restart_service) unless SMOKE_DESTRUCTIVE=1.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from http.cookiejar import CookieJar

BASE = os.environ.get("MESHPOINT_BASE", "http://192.168.0.141:8080").rstrip("/")
USER = os.environ.get("MESHPOINT_USER", "admin")
PASSWORD = os.environ.get("MESHPOINT_PASSWORD", "")
DESTRUCTIVE = os.environ.get("SMOKE_DESTRUCTIVE", "") == "1"

FAILURES: list[str] = []


def fail(msg: str) -> None:
    FAILURES.append(msg)
    print(f"FAIL: {msg}")


def ok(msg: str) -> None:
    print(f"OK: {msg}")


def main() -> int:
    if not PASSWORD:
        print("Set MESHPOINT_PASSWORD", file=sys.stderr)
        return 2

    cj = CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))

    def req(method: str, path: str, body: dict | None = None, timeout: float = 20):
        data = json.dumps(body).encode() if body is not None else None
        headers = {"Content-Type": "application/json"} if body is not None else {}
        request = urllib.request.Request(
            BASE + path, data=data, headers=headers, method=method,
        )
        try:
            with opener.open(request, timeout=timeout) as resp:
                raw = resp.read().decode()
                return resp.status, json.loads(raw) if raw else {}
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode()
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                payload = {"raw": raw[:300]}
            return exc.code, payload

    st, body = req("POST", "/api/auth/login", {"username": USER, "password": PASSWORD})
    if st != 200:
        fail(f"login {st} {body}")
        return 1
    ok(f"login role={body.get('role')}")

    st, ident = req("GET", "/api/identity")
    if st != 200 or ident.get("setup_required"):
        fail(f"identity {st} {ident}")
    else:
        ok(f"identity device={ident.get('device_name')}")

    st, cfg = req("GET", "/api/config")
    if st != 200:
        fail(f"config GET {st}")
        return 1
    tx = cfg.get("transmit", {})
    orig = {"long_name": tx.get("long_name"), "short_name": tx.get("short_name")}

    st, j = req(
        "PUT",
        "/api/config/identity",
        {"long_name": "Smoke Test", "short_name": "SMK1"},
    )
    if st != 200:
        fail(f"identity PUT {st} {j}")
    else:
        ok("identity round-trip PUT")

    req("PUT", "/api/config/identity", orig)

    st, acts = req("GET", "/api/dangerous/actions")
    ids = [a["id"] for a in acts.get("actions", [])]
    if st != 200 or "restart_concentrator" not in ids:
        fail(f"dangerous actions {st} {ids}")
    else:
        ok(f"dangerous actions ({len(ids)})")

    for action_id in ("force_nodeinfo", "wipe_phantom_nodes", "restart_concentrator"):
        st, j = req("POST", "/api/dangerous/invoke", {"action_id": action_id}, timeout=45)
        if st != 200:
            fail(f"{action_id} HTTP {st}")
        elif not j.get("success"):
            fail(f"{action_id} {j.get('message')}")
        else:
            ok(f"{action_id}: {j.get('message')}")

    st, cfg2 = req("GET", "/api/config")
    relay = (cfg2.get("relay") or cfg2.get("transmit", {}).get("relay"))
    if st == 200 and relay is not None:
        ok("config GET includes relay settings")
    else:
        fail(f"relay shape {st} {cfg2.get('relay')}")

    if DESTRUCTIVE:
        st, j = req("POST", "/api/dangerous/invoke", {"action_id": "clear_database"})
        if st == 200 and j.get("success"):
            ok("clear_database (destructive)")
        else:
            fail(f"clear_database {st} {j}")

    if FAILURES:
        print(f"\n{len(FAILURES)} failure(s)")
        return 1
    print("\nAll smoke checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
