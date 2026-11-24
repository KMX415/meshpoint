"""Apply real host-radio settings, bypassing virtual companion no-op commands."""

from __future__ import annotations

import asyncio
import json
import urllib.request
from pathlib import Path

from src.radio.pimesh_supervisor import PROVISION, read_json

MODES = ("monitor", "forward", "no_tx")


async def _login():
    credentials = json.loads(Path("config/openhop-auth.json").read_text())
    auth = await asyncio.to_thread(_post, "/auth/login", {
        "username": "admin", "password": credentials["password"], "client_id": "meshpoint",
    })
    token = auth.get("token") or auth.get("data", {}).get("token")
    if not token:
        raise RuntimeError("MeshCore daemon authentication failed")
    return token


def _read_mode(token):
    request = urllib.request.Request("http://127.0.0.1:8000/api/stats",
        headers={"Authorization": "Bearer " + token})
    with urllib.request.urlopen(request, timeout=15) as response:
        result = json.load(response)
    mode = result.get("config", {}).get("repeater", {}).get("mode")
    if mode not in MODES:
        raise RuntimeError("MeshCore mode readback unavailable")
    return {"mode": mode, "modes": list(MODES)}


async def read_mode():
    return await asyncio.to_thread(_read_mode, await _login())


async def apply_mode(mode):
    if mode not in MODES:
        raise ValueError("Unsupported MeshCore mode")
    token = await _login()
    result = await asyncio.to_thread(_post, "/api/set_mode", {"mode": mode}, token)
    if result.get("persisted") is not True:
        raise RuntimeError("MeshCore mode persistence unconfirmed")
    actual = await asyncio.to_thread(_read_mode, token)
    if actual["mode"] != mode:
        raise RuntimeError("MeshCore mode readback did not match")
    return actual


def _post(path, payload, token=""):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    request = urllib.request.Request(
        "http://127.0.0.1:8000" + path,
        data=json.dumps(payload).encode(),
        headers=headers,
    )
    with urllib.request.urlopen(request, timeout=15) as response:
        result = json.load(response)
    if not result.get("success", True):
        raise RuntimeError("MeshCore daemon rejected radio configuration")
    return result


async def apply_radio(mc_tx, preset=None, tx_power_dbm=None):
    region = read_json(PROVISION).get("region")
    limits = {"US": (902, 928), "EU_868": (863, 870), "ANZ": (915, 928)}
    if region not in limits:
        raise ValueError("Unsupported PiMesh region")
    lo, hi = limits[region]
    if (
        preset is not None
        and not lo
        <= preset.frequency_mhz - preset.bandwidth_khz / 2000
        < preset.frequency_mhz + preset.bandwidth_khz / 2000
        <= hi
    ):
        raise ValueError("Preset is outside the provisioned PiMesh region")
    payload = {}
    if preset is not None:
        payload.update(
            frequency=round(preset.frequency_mhz * 1e6),
            bandwidth=round(preset.bandwidth_khz * 1000),
            spreading_factor=preset.spreading_factor,
            coding_rate=preset.coding_rate,
        )
    if tx_power_dbm is not None:
        if not 2 <= tx_power_dbm <= 22:
            raise ValueError("PiMesh chip power must be between 2 and 22 dBm")
        payload["tx_power"] = tx_power_dbm
    if not payload:
        return
    credentials = json.loads(Path("config/openhop-auth.json").read_text())
    auth = await asyncio.to_thread(
        _post,
        "/auth/login",
        {
            "username": "admin",
            "password": credentials["password"],
            "client_id": "meshpoint",
        },
    )
    token = auth.get("token") or auth.get("data", {}).get("token")
    if not token:
        raise RuntimeError("MeshCore daemon authentication failed")
    result = await asyncio.to_thread(_post, "/api/update_radio_config", payload, token)
    if not result.get("data", {}).get("live_update"):
        raise RuntimeError(
            "Settings saved by daemon but not applied; restart the MeshCore backend"
        )
    actual = await mc_tx.refresh_radio_info()
    if (
        actual is None
        or (
            preset is not None
            and (
                abs(actual.frequency_mhz - preset.frequency_mhz) > 0.002
                or abs(actual.bandwidth_khz - preset.bandwidth_khz) > 0.1
                or actual.spreading_factor != preset.spreading_factor
                or actual.coding_rate != preset.coding_rate
            )
        )
        or (tx_power_dbm is not None and actual.tx_power != tx_power_dbm)
    ):
        raise RuntimeError("MeshCore radio readback did not match requested settings")
