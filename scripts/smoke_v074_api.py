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
WARNINGS: list[str] = []


def fail(msg: str) -> None:
    FAILURES.append(msg)
    print(f"FAIL: {msg}")


def warn(msg: str) -> None:
    WARNINGS.append(msg)
    print(f"WARN: {msg}")


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
    ok("config GET")

    tx = cfg.get("transmit", {})
    orig_identity = {"long_name": tx.get("long_name"), "short_name": tx.get("short_name")}

    st, j = req(
        "PUT",
        "/api/config/identity",
        {"long_name": "Smoke Test", "short_name": "SMK1"},
    )
    if st != 200:
        fail(f"identity PUT {st} {j}")
    else:
        ok("identity round-trip PUT")
    req("PUT", "/api/config/identity", orig_identity)

    orig_tx_power = tx.get("tx_power_dbm")
    st, j = req("PUT", "/api/config/transmit", {"tx_power_dbm": 17})
    if st != 200 or not j.get("saved"):
        fail(f"transmit tx_power PUT {st} {j}")
    else:
        ok("transmit tx_power PUT")
    if orig_tx_power is not None:
        req("PUT", "/api/config/transmit", {"tx_power_dbm": orig_tx_power})

    relay = tx.get("relay") or cfg.get("relay") or {}
    orig_relay_rate = relay.get("max_relay_per_minute")
    if orig_relay_rate is not None:
        st, j = req(
            "PUT",
            "/api/config/transmit",
            {"relay": {"max_relay_per_minute": orig_relay_rate}},
        )
        if st != 200:
            fail(f"transmit relay PUT {st} {j}")
        else:
            ok("transmit relay round-trip PUT")

    radio = cfg.get("radio", {})
    orig_hop = tx.get("hop_limit")
    if orig_hop is not None:
        st, j = req("PUT", "/api/config/transmit", {"hop_limit": orig_hop})
        if st != 200:
            fail(f"transmit hop_limit PUT {st} {j}")
        else:
            ok("transmit hop_limit PUT")

    if radio.get("region"):
        st, j = req(
            "PUT",
            "/api/config/radio",
            {"preset": radio.get("current_preset") or "LONG_FAST"},
        )
        if st != 200:
            fail(f"radio preset PUT {st} {j}")
        else:
            ok("radio preset PUT (no region change)")

    channels = cfg.get("channels") or []
    if channels:
        ch_payload = [
            {
                "index": ch.get("index", -1),
                "name": ch.get("name", ""),
                "psk_b64": ch.get("psk_b64", ""),
                "enabled": ch.get("enabled", True),
            }
            for ch in channels
        ]
        st, j = req("PUT", "/api/config/channels", {"channels": ch_payload})
        if st != 200:
            fail(f"channels PUT {st} {j}")
        else:
            ok(f"channels round-trip PUT ({len(ch_payload)} rows)")

    ni = cfg.get("nodeinfo") or {}
    orig_interval = ni.get("interval_minutes")
    if orig_interval is not None:
        test_interval = 180 if orig_interval != 180 else 360
        st, j = req("PUT", "/api/config/nodeinfo", {"interval_minutes": test_interval})
        if st != 200:
            fail(f"nodeinfo interval PUT {st} {j}")
        else:
            ok("nodeinfo interval PUT")
        req("PUT", "/api/config/nodeinfo", {"interval_minutes": orig_interval})

    st, j = req("POST", "/api/config/nodeinfo/send", timeout=45)
    if st != 200:
        fail(f"nodeinfo send POST {st} {j}")
    else:
        ok("nodeinfo send POST")

    mqtt_orig = cfg.get("mqtt") or {}
    st, j = req(
        "PUT",
        "/api/config/mqtt",
        {
            "enabled": mqtt_orig.get("enabled", False),
            "broker_host": mqtt_orig.get("broker_host", "mqtt.meshtastic.org"),
            "broker_port": mqtt_orig.get("broker_port", 1883),
            "topic_root": mqtt_orig.get("topic_root", "msh"),
            "region_segment": mqtt_orig.get("region_segment", "US"),
            "encrypted": mqtt_orig.get("encrypted", True),
            "gateway_id": "",
        },
    )
    if st != 200 or not j.get("saved"):
        fail(f"mqtt PUT {st} {j}")
    else:
        ok("mqtt round-trip PUT")

    st, j = req("PUT", "/api/config/gps", {"source": "static"})
    if st in (404, 405):
        ok("gps PUT not wired (expected skip)")
    elif st == 200:
        ok("gps PUT (unexpectedly implemented)")
    else:
        warn(f"gps PUT status {st}")

    st, j = req(
        "POST",
        "/api/auth/change_password",
        {"current_password": "wrong-password", "new_password": "newpassword1"},
    )
    if st != 401:
        fail(f"change_password wrong current expected 401 got {st}")
    else:
        ok("change_password rejects wrong current password")

    st, j = req(
        "POST",
        "/api/auth/change_password",
        {"current_password": PASSWORD, "new_password": "short"},
    )
    if st != 400:
        fail(f"change_password short password expected 400 got {st}")
    else:
        ok("change_password rejects short new password")

    st, settings = req("GET", "/api/config/auth_settings")
    if st != 200:
        fail(f"auth_settings GET {st}")
    else:
        ok(
            "auth_settings GET "
            f"attempts={settings.get('lockout_attempts')} "
            f"cooldown={settings.get('lockout_cooldown_minutes')}"
        )

    orig_attempts = settings.get("lockout_attempts", 5)
    orig_cooldown = settings.get("lockout_cooldown_minutes", 5)
    st, j = req(
        "PUT",
        "/api/config/auth_lockout",
        {
            "lockout_attempts": orig_attempts,
            "lockout_cooldown_minutes": orig_cooldown,
        },
    )
    if st != 200:
        fail(f"auth_lockout PUT {st} {j}")
    else:
        ok("auth_lockout round-trip PUT")

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
    relay2 = (cfg2.get("relay") or cfg2.get("transmit", {}).get("relay"))
    if st == 200 and relay2 is not None:
        ok("config GET includes relay settings")
    else:
        fail(f"relay shape {st} {cfg2.get('relay')}")

    if DESTRUCTIVE:
        st, j = req("POST", "/api/dangerous/invoke", {"action_id": "clear_database"})
        if st == 200 and j.get("success"):
            ok("clear_database (destructive)")
        else:
            fail(f"clear_database {st} {j}")

    if WARNINGS:
        print(f"\n{len(WARNINGS)} warning(s) (ship blockers if MQTT/GPS routes missing)")
    if FAILURES:
        print(f"\n{len(FAILURES)} failure(s)")
        return 1
    print("\nAll smoke checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
