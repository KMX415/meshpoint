"""Enrich MeshCore node rows from the companion device's contact list.

The MeshCore companion (USB-attached firmware on a Heltec/T-Echo/etc.)
keeps a friendly-name -> public-key map for every node it has heard.
We can pull that list and use it to populate ``long_name`` on
``nodes`` rows that only have a public-key prefix as their identifier
(captured from over-the-air adverts whose payload didn't carry the
name in a field we recognise).

Two entry points:
* ``setup_meshcore_contact_enrichment`` — register a packet callback
  that *throttled* triggers a contact-list sync whenever a MeshCore
  packet is observed.
* ``sync_meshcore_contacts_to_nodes`` — one-shot sync used at startup
  and called by the throttled per-packet trigger.

Throttling is important: ``MeshCoreTxClient.get_contacts`` hits the
companion's serial port with a 10-second timeout and logs at INFO,
so firing it on every received MeshCore packet would saturate the
companion bus and spam the log on a busy mesh. Names rarely change,
so we cap real syncs to once every ``_SYNC_THROTTLE_SECONDS``.
"""

from __future__ import annotations

import asyncio
import logging
import time

from src.models.packet import Packet, Protocol

logger = logging.getLogger(__name__)

_SYNC_THROTTLE_SECONDS = 300.0


class _SyncThrottle:
    """Module-level throttle for packet-driven contact-list syncs."""

    def __init__(self, min_interval_seconds: float) -> None:
        self._min_interval = min_interval_seconds
        self._last_sync_at: float = 0.0
        self._in_flight: bool = False

    def should_run(self) -> bool:
        if self._in_flight:
            return False
        return (time.monotonic() - self._last_sync_at) >= self._min_interval

    def mark_started(self) -> None:
        self._in_flight = True

    def mark_done(self) -> None:
        self._in_flight = False
        self._last_sync_at = time.monotonic()


_throttle = _SyncThrottle(_SYNC_THROTTLE_SECONDS)


def setup_meshcore_contact_enrichment(coord, meshcore_tx=None) -> None:
    """Register a throttled packet callback that re-syncs MeshCore contact
    names whenever a MeshCore packet flows through the pipeline.

    Safe to call when ``meshcore_tx`` is None (Meshtastic-only installs):
    the callback is simply not registered.
    """
    if meshcore_tx is None:
        return

    def on_meshcore_packet(packet: Packet) -> None:
        if packet.protocol != Protocol.MESHCORE or not packet.source_id:
            return
        if not _throttle.should_run():
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        loop.create_task(
            _throttled_sync(coord, meshcore_tx, packet.source_id)
        )

    coord.on_packet(on_meshcore_packet)


async def _throttled_sync(coord, meshcore_tx, source_id: str) -> None:
    """Wrapper that flips the throttle flags before/after a sync run."""
    _throttle.mark_started()
    try:
        await sync_meshcore_contacts_to_nodes(coord, meshcore_tx, source_id)
    finally:
        _throttle.mark_done()


async def sync_meshcore_contacts_to_nodes(
    coord,
    meshcore_tx,
    source_id: str = "",
) -> int:
    """Pull the companion's contact list and back-fill matching node rows.

    Returns the number of rows updated. Best-effort: every failure
    path returns 0 silently (with a debug log) rather than raising,
    so this function is safe to call from a background task.
    """
    if not meshcore_tx or not meshcore_tx.connected:
        return 0

    source = source_id.lower().lstrip("!")
    updated = 0
    try:
        contacts = await meshcore_tx.get_contacts()
    except Exception:
        logger.debug("MeshCore contact node enrichment failed", exc_info=True)
        return 0

    for contact in contacts:
        pk = str(contact.get("public_key", "")).lower().lstrip("!")
        name = str(contact.get("name", "")).strip()
        if not pk or not name or _is_hex_identifier(name):
            continue
        prefixes = _meshcore_pubkey_prefixes(pk)
        if source and not any(
            source.startswith(p) or p.startswith(source) for p in prefixes
        ):
            continue
        short_name = name[:4]
        for prefix in prefixes:
            cursor = await coord.node_repo._db.execute(
                """
                UPDATE nodes
                SET long_name = ?,
                    short_name = CASE
                        WHEN short_name IS NULL
                          OR short_name = ''
                          OR LOWER(LTRIM(short_name, '!')) = LOWER(SUBSTR(LTRIM(node_id, '!'), 1, 4))
                            THEN ?
                        ELSE short_name
                    END
                WHERE protocol = 'meshcore'
                  AND LOWER(LTRIM(node_id, '!')) LIKE ?
                """,
                (name, short_name, prefix + "%"),
            )
            if cursor.rowcount and cursor.rowcount > 0:
                updated += cursor.rowcount
                break

    if updated:
        await coord.node_repo._db.commit()
        logger.info(
            "MeshCore contact names applied to %d node row(s)", updated,
        )
    return updated


def _meshcore_pubkey_prefixes(pubkey: str) -> tuple[str, ...]:
    """Yield candidate prefixes (longest first) for a node-id LIKE match."""
    lengths = (16, 12, 10, 8, len(pubkey))
    return tuple(
        dict.fromkeys(pubkey[:n] for n in lengths if len(pubkey) >= n)
    )


def _is_hex_identifier(value: str) -> bool:
    """True when ``value`` is a hex string long enough to be a node-id."""
    candidate = value.lower().lstrip("!")
    try:
        int(candidate, 16)
        return len(candidate) >= 6
    except ValueError:
        return False
