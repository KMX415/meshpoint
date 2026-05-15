from __future__ import annotations

import logging

from src.models.packet import Packet, Protocol

logger = logging.getLogger(__name__)


def setup_meshcore_contact_enrichment(coord, meshcore_tx=None) -> None:
    """Keep MeshCore node rows named from the companion contact list."""
    if meshcore_tx is None:
        return

    def on_meshcore_packet(packet: Packet) -> None:
        if packet.protocol != Protocol.MESHCORE or not packet.source_id:
            return

        import asyncio
        try:
            asyncio.get_running_loop().create_task(
                sync_meshcore_contacts_to_nodes(
                    coord, meshcore_tx, packet.source_id
                )
            )
        except RuntimeError:
            pass

    coord.on_packet(on_meshcore_packet)


async def sync_meshcore_contacts_to_nodes(
    coord,
    meshcore_tx,
    source_id: str = "",
) -> int:
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
        if source and not any(source.startswith(p) or p.startswith(source) for p in prefixes):
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
        logger.info("MeshCore contact names applied to %d node row(s)", updated)
    return updated


def _meshcore_pubkey_prefixes(pubkey: str) -> tuple[str, ...]:
    lengths = (16, 12, 10, 8, len(pubkey))
    return tuple(dict.fromkeys(pubkey[:n] for n in lengths if len(pubkey) >= n))


def _is_hex_identifier(value: str) -> bool:
    candidate = value.lower().lstrip("!")
    try:
        int(candidate, 16)
        return len(candidate) >= 6
    except ValueError:
        return False
