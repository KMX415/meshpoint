"""Parse MeshCore companion contact-list command results.

``meshcore.commands.get_contacts()`` returns ``None`` on its own
timeout, an ERROR ``Event`` when the companion rejects, or a
CONTACTS ``Event`` whose ``payload`` shape varies by firmware.
This module owns that defensive parse so MeshCoreTxClient stays thin.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Optional

from src.models.meshcore_position import meshcore_position

logger = logging.getLogger(__name__)

# Hot paths (Messages tab name resolve, contact picker) must not hammer
# the companion serial bus. Prefer this TTL cache over a live fetch.
DEFAULT_CONTACTS_CACHE_TTL_SECONDS = 60.0


class MeshcoreContactCache:
    """TTL cache for companion contact rows."""

    def __init__(
        self,
        ttl_seconds: float = DEFAULT_CONTACTS_CACHE_TTL_SECONDS,
    ) -> None:
        self._ttl = ttl_seconds
        self._rows: list[dict] = []
        self._fetched_at: float = 0.0

    def get_fresh(self) -> Optional[list[dict]]:
        if not self._fetched_at:
            return None
        if (time.monotonic() - self._fetched_at) >= self._ttl:
            return None
        return list(self._rows)

    def get_stale(self) -> list[dict]:
        """Last known roster, even if TTL expired (empty if never fetched)."""
        return list(self._rows)

    def store(self, rows: list[dict]) -> None:
        self._rows = list(rows)
        self._fetched_at = time.monotonic()

    def note_soft_fail(self) -> None:
        """Refresh TTL after a timeout/error so callers back off.

        Without this, an empty cache causes every Messages/enrichment
        caller to burn another 5s live ``get_contacts`` and wedge the
        companion command channel.
        """
        self._fetched_at = time.monotonic()

    def invalidate(self) -> None:
        self._fetched_at = 0.0


class MeshcoreContactParser:
    """Normalize and extract contact rows from a get_contacts result."""

    @staticmethod
    def normalize_payload(payload: Any) -> list[dict]:
        """Accept both dict-keyed-by-pubkey and list formats.

        Defensively filters values to dicts only. Some firmware
        revisions return mixed int/string values alongside contact
        dicts; non-dicts are dropped so shape drift cannot crash
        callers.
        """
        if isinstance(payload, dict):
            return [v for v in payload.values() if isinstance(v, dict)]
        if isinstance(payload, list):
            return [e for e in payload if isinstance(e, dict)]
        return []

    @classmethod
    def from_command_result(cls, result: Any) -> list[dict]:
        """Turn a library get_contacts return value into contact rows.

        ``None`` (library timeout) and ERROR events become ``[]`` with
        a warning. Valid payloads become ``{index, name, public_key,
        last_seen, adv_lat, adv_lon}`` rows.
        """
        if result is None:
            logger.warning(
                "get_contacts: companion returned no event "
                "(busy or timed out)"
            )
            return []

        if cls._is_error_event(result):
            detail = cls._error_detail(result)
            logger.warning(
                "get_contacts: companion error%s",
                f" ({detail})" if detail else "",
            )
            return []

        entries = cls.normalize_payload(getattr(result, "payload", None))
        return cls._entries_to_contacts(entries)

    @staticmethod
    def _is_error_event(result: Any) -> bool:
        try:
            from meshcore import EventType
        except Exception:
            return False
        event_type = getattr(result, "type", None)
        return event_type == EventType.ERROR

    @staticmethod
    def _error_detail(result: Any) -> str:
        payload = getattr(result, "payload", None)
        if not isinstance(payload, dict):
            return ""
        return str(
            payload.get("reason") or payload.get("error") or payload
        )

    @staticmethod
    def _entries_to_contacts(entries: list[dict]) -> list[dict]:
        contacts: list[dict] = []
        for i, entry in enumerate(entries):
            if not isinstance(entry, dict):
                continue
            try:
                name = entry.get("adv_name") or entry.get("name") or ""
                pk = entry.get("public_key", "")
                if pk:
                    position = meshcore_position(entry.get("adv_lat"), entry.get("adv_lon"))
                    contacts.append({
                        "index": i,
                        "name": name,
                        "public_key": pk,
                        "last_seen": entry.get("lastmod", 0),
                        "adv_lat": position[0] if position else None,
                        "adv_lon": position[1] if position else None,
                    })
            except Exception:
                logger.debug(
                    "get_contacts: skipping malformed entry at index %d",
                    i,
                    exc_info=True,
                )
        return contacts
