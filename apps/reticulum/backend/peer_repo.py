"""SQLite repository for the Reticulum/LXMF peer roster.

Moved verbatim from ``src/storage/reticulum_peer_repository.py`` as part of
the core->plugin extraction. The ``reticulum_peers`` table itself stays in
core's ``src/storage/database.py`` schema (precedent: the DAPNET plugin
kept using the shared ``packets`` table) -- this class just reads/writes
it via the shared ``DatabaseManager`` handed in from ``pipeline.database``.

Peers are learned purely from received announces (lxmf.delivery,
lxmf.propagation, nomadnetwork.node) -- there is no NodeInfo-style packet
to enrich this from. Chat history lives in the existing ``messages`` table
(protocol='reticulum'), not here.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone

from src.storage.database import DatabaseManager

logger = logging.getLogger(__name__)


@dataclass
class ReticulumPeer:
    destination_hash: str
    display_name: str
    aspect: str
    first_seen: str
    last_seen: str

    def to_dict(self) -> dict:
        return {
            "destination_hash": self.destination_hash,
            "display_name": self.display_name or self.destination_hash,
            "aspect": self.aspect,
            "first_seen": self.first_seen,
            "last_seen": self.last_seen,
        }


class ReticulumPeerRepository:
    """Upsert-on-announce roster of known Reticulum destinations."""

    def __init__(self, db: DatabaseManager):
        self._db = db

    async def record_announce(
        self, destination_hash: str, display_name: str, aspect: str,
    ) -> None:
        now = datetime.now(timezone.utc).isoformat()
        existing = await self._db.fetch_one(
            "SELECT first_seen FROM reticulum_peers WHERE destination_hash = ?",
            (destination_hash,),
        )
        if existing:
            if display_name:
                # A later announce with no decodable display name (no
                # app_data, or a decode failure) must not blank out a
                # name we already learned from an earlier one -- only
                # overwrite when this announce actually carries one.
                await self._db.execute(
                    """UPDATE reticulum_peers
                       SET display_name = ?, aspect = ?, last_seen = ?
                       WHERE destination_hash = ?""",
                    (display_name, aspect, now, destination_hash),
                )
            else:
                await self._db.execute(
                    """UPDATE reticulum_peers
                       SET aspect = ?, last_seen = ?
                       WHERE destination_hash = ?""",
                    (aspect, now, destination_hash),
                )
        else:
            await self._db.execute(
                """INSERT INTO reticulum_peers
                   (destination_hash, display_name, aspect, first_seen, last_seen)
                   VALUES (?, ?, ?, ?, ?)""",
                (destination_hash, display_name, aspect, now, now),
            )
        await self._db.commit()

    async def count(self, aspect: str | None = None) -> int:
        if aspect:
            row = await self._db.fetch_one(
                "SELECT COUNT(*) AS n FROM reticulum_peers WHERE aspect = ?",
                (aspect,),
            )
        else:
            row = await self._db.fetch_one("SELECT COUNT(*) AS n FROM reticulum_peers")
        return int(row["n"]) if row else 0

    async def list_peers(
        self, aspect: str | None = None, limit: int | None = None,
    ) -> list[ReticulumPeer]:
        sql = "SELECT * FROM reticulum_peers"
        params: tuple = ()
        if aspect:
            sql += " WHERE aspect = ?"
            params = (aspect,)
        sql += " ORDER BY last_seen DESC"
        if limit:
            sql += f" LIMIT {int(limit)}"
        rows = await self._db.fetch_all(sql, params)
        return [
            ReticulumPeer(
                destination_hash=r["destination_hash"],
                display_name=r["display_name"] or "",
                aspect=r["aspect"],
                first_seen=r["first_seen"],
                last_seen=r["last_seen"],
            )
            for r in rows
        ]
