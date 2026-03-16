"""Check whether a newer version is available on GitHub."""

from __future__ import annotations

import logging
import re
import time

import asyncio
import urllib.request

from fastapi import APIRouter

from src.version import __version__

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/device", tags=["device"])

_VERSION_URL = (
    "https://raw.githubusercontent.com/KMX415/meshpoint/main/src/version.py"
)
_VERSION_RE = re.compile(r'__version__\s*=\s*["\']([^"\']+)["\']')
_CACHE_TTL_SECONDS = 300

_cache: dict[str, object] = {"result": None, "expires": 0}


def _parse_version(version_str: str) -> tuple[int, ...]:
    return tuple(int(x) for x in version_str.split("."))


def _fetch_remote_version_sync() -> str | None:
    try:
        req = urllib.request.Request(_VERSION_URL, method="GET")
        with urllib.request.urlopen(req, timeout=10) as resp:
            text = resp.read().decode()
            match = _VERSION_RE.search(text)
            return match.group(1) if match else None
    except Exception:
        logger.debug("Failed to fetch remote version", exc_info=True)
        return None


async def _fetch_remote_version() -> str | None:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _fetch_remote_version_sync)


@router.get("/update-check")
async def update_check():
    now = time.time()
    if _cache["result"] and now < _cache["expires"]:
        return _cache["result"]

    remote_version = await _fetch_remote_version()

    if not remote_version:
        result = {
            "update_available": False,
            "local_version": __version__,
            "remote_version": None,
            "error": "Could not reach GitHub",
        }
    else:
        try:
            available = _parse_version(remote_version) > _parse_version(__version__)
        except ValueError:
            available = False
        result = {
            "update_available": available,
            "local_version": __version__,
            "remote_version": remote_version,
        }

    _cache["result"] = result
    _cache["expires"] = now + _CACHE_TTL_SECONDS

    return result
