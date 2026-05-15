from __future__ import annotations

import logging
from pathlib import Path

import aiosqlite

logger = logging.getLogger(__name__)

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS nodes (
    node_id       TEXT PRIMARY KEY,
    long_name     TEXT,
    short_name    TEXT,
    hardware_model TEXT,
    firmware_version TEXT,
    protocol      TEXT NOT NULL DEFAULT 'meshtastic',
    role          TEXT,
    latitude      REAL,
    longitude     REAL,
    altitude      REAL,
    last_heard    TEXT NOT NULL,
    first_seen    TEXT NOT NULL,
    packet_count  INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS packets (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    packet_id        TEXT NOT NULL,
    source_id        TEXT NOT NULL,
    destination_id   TEXT NOT NULL,
    protocol         TEXT NOT NULL,
    packet_type      TEXT NOT NULL,
    hop_limit        INTEGER DEFAULT 0,
    hop_start        INTEGER DEFAULT 0,
    channel_hash     INTEGER DEFAULT 0,
    want_ack         INTEGER DEFAULT 0,
    via_mqtt         INTEGER DEFAULT 0,
    relay_node       INTEGER DEFAULT 0,
    decoded_payload  TEXT,
    decrypted        INTEGER DEFAULT 0,
    rssi             REAL,
    snr              REAL,
    frequency_mhz    REAL,
    spreading_factor INTEGER,
    bandwidth_khz    REAL,
    capture_source   TEXT,
    timestamp        TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS telemetry (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    node_id               TEXT NOT NULL,
    battery_level         REAL,
    voltage               REAL,
    temperature           REAL,
    humidity              REAL,
    barometric_pressure   REAL,
    channel_utilization   REAL,
    air_util_tx           REAL,
    uptime_seconds        INTEGER,
    timestamp             TEXT NOT NULL,
    FOREIGN KEY (node_id) REFERENCES nodes(node_id)
);

CREATE INDEX IF NOT EXISTS idx_packets_timestamp ON packets(timestamp);
CREATE INDEX IF NOT EXISTS idx_packets_source ON packets(source_id);
CREATE INDEX IF NOT EXISTS idx_packets_protocol ON packets(protocol);
CREATE INDEX IF NOT EXISTS idx_packets_type ON packets(packet_type);
CREATE INDEX IF NOT EXISTS idx_telemetry_node ON telemetry(node_id);
CREATE INDEX IF NOT EXISTS idx_telemetry_timestamp ON telemetry(timestamp);

CREATE TABLE IF NOT EXISTS messages (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    direction     TEXT NOT NULL,
    text          TEXT NOT NULL,
    node_id       TEXT NOT NULL,
    node_name     TEXT,
    protocol      TEXT NOT NULL,
    channel       INTEGER NOT NULL DEFAULT 0,
    timestamp     TEXT NOT NULL,
    status        TEXT NOT NULL DEFAULT 'sent',
    packet_id     TEXT,
    rssi          REAL,
    snr           REAL,
    rx_count      INTEGER NOT NULL DEFAULT 1
);

CREATE INDEX IF NOT EXISTS idx_messages_node ON messages(node_id);
CREATE INDEX IF NOT EXISTS idx_messages_timestamp ON messages(timestamp);
CREATE INDEX IF NOT EXISTS idx_messages_direction ON messages(direction);
"""


class DatabaseManager:
    """Async SQLite connection manager with schema initialization."""

    def __init__(self, db_path: str):
        self._db_path = db_path
        self._connection: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        self._connection = await aiosqlite.connect(self._db_path)
        self._connection.row_factory = aiosqlite.Row
        await self._connection.executescript(SCHEMA_SQL)
        await self._run_migrations()
        await self._connection.commit()
        logger.info("Database connected: %s", self._db_path)

    async def _run_migrations(self) -> None:
        cursor = await self._connection.execute("PRAGMA table_info(packets)")
        pkt_cols = {row[1] for row in await cursor.fetchall()}
        if "relay_node" not in pkt_cols:
            await self._connection.execute(
                "ALTER TABLE packets ADD COLUMN relay_node INTEGER DEFAULT 0"
            )
            logger.info("Migration: added 'relay_node' column to packets table")

        cursor = await self._connection.execute("PRAGMA table_info(nodes)")
        columns = {row[1] for row in await cursor.fetchall()}
        if "role" not in columns:
            await self._connection.execute("ALTER TABLE nodes ADD COLUMN role TEXT")
            logger.info("Migration: added 'role' column to nodes table")

        cursor = await self._connection.execute("PRAGMA table_info(messages)")
        msg_cols = {row[1] for row in await cursor.fetchall()}
        if msg_cols and "rssi" not in msg_cols:
            await self._connection.execute("ALTER TABLE messages ADD COLUMN rssi REAL")
            await self._connection.execute("ALTER TABLE messages ADD COLUMN snr REAL")
            logger.info("Migration: added signal columns to messages table")
        if msg_cols and "rx_count" not in msg_cols:
            await self._connection.execute(
                "ALTER TABLE messages ADD COLUMN rx_count INTEGER NOT NULL DEFAULT 1"
            )
            logger.info("Migration: added rx_count column to messages table")

        await self._cleanup_cross_protocol_name_contamination()
        await self._cleanup_meshcore_placeholder_names()

    async def _cleanup_cross_protocol_name_contamination(self) -> None:
        """Repair Meshtastic node rows whose long_name was overwritten by a
        MeshCore contact name due to the unscoped fallback in versions <0.6.7.

        Idempotent: only matches rows where a Meshtastic long_name exactly
        matches a long_name on a `mc:%` MeshCore row (the canonical source of
        contamination). The Meshtastic row is reset to NULL so the next
        NodeInfo broadcast from the real node repopulates it correctly.
        """
        cursor = await self._connection.execute(
            """
            UPDATE nodes
            SET long_name = NULL
            WHERE protocol = 'meshtastic'
              AND long_name IS NOT NULL
              AND long_name IN (
                  SELECT long_name FROM nodes
                  WHERE protocol = 'meshcore'
                    AND node_id LIKE 'mc:%'
                    AND long_name IS NOT NULL
              )
            """
        )
        if cursor.rowcount and cursor.rowcount > 0:
            logger.warning(
                "Migration: cleared %d cross-protocol contaminated Meshtastic "
                "node row(s); long_name will be repopulated on next NodeInfo",
                cursor.rowcount,
            )

    async def _cleanup_meshcore_placeholder_names(self) -> None:
        """Clear MeshCore rows that accidentally stored IDs as display names."""
        cursor = await self._connection.execute(
            """
            UPDATE nodes
            SET long_name = NULL,
                short_name = CASE
                    WHEN short_name IS NOT NULL
                     AND LOWER(LTRIM(short_name, '!')) = LOWER(SUBSTR(LTRIM(node_id, '!'), 1, 4))
                        THEN NULL
                    ELSE short_name
                END
            WHERE protocol = 'meshcore'
              AND long_name IS NOT NULL
              AND LOWER(LTRIM(long_name, '!')) = LOWER(LTRIM(node_id, '!'))
            """
        )
        if cursor.rowcount and cursor.rowcount > 0:
            logger.warning(
                "Migration: cleared %d MeshCore node placeholder name(s); "
                "names will repopulate on the next valid advert",
                cursor.rowcount,
            )

    async def disconnect(self) -> None:
        if self._connection:
            await self._connection.close()
            self._connection = None
            logger.info("Database disconnected")

    @property
    def connection(self) -> aiosqlite.Connection:
        if self._connection is None:
            raise RuntimeError("Database not connected. Call connect() first.")
        return self._connection

    async def execute(self, sql: str, params: tuple = ()) -> aiosqlite.Cursor:
        return await self.connection.execute(sql, params)

    async def fetch_one(self, sql: str, params: tuple = ()) -> dict | None:
        cursor = await self.execute(sql, params)
        row = await cursor.fetchone()
        return dict(row) if row else None

    async def fetch_all(self, sql: str, params: tuple = ()) -> list[dict]:
        cursor = await self.execute(sql, params)
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]

    async def commit(self) -> None:
        await self.connection.commit()
