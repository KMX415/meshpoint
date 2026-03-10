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
CREATE INDEX IF NOT EXISTS idx_telemetry_node ON telemetry(node_id);
CREATE INDEX IF NOT EXISTS idx_telemetry_timestamp ON telemetry(timestamp);
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
        await self._connection.commit()
        logger.info("Database connected: %s", self._db_path)

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
