"""Tests for ``DatabaseManager`` schema migrations.

Two distinct migrations are exercised here:

1. The cross-protocol name contamination cleanup. Versions <0.6.7 had an
   unscoped MeshCore name fallback in ``src/api/server.py::_save_and_notify``
   that wrote a MeshCore contact's ``long_name`` into a Meshtastic node's
   row whenever an inbound Meshtastic message lacked a name. The fallback
   is now scoped to MeshCore packets only, and a startup migration cleans
   up rows poisoned by the prior bug.
2. The ``packets.relay_node`` column added in PR #45 to surface the
   Meshtastic header byte 15 (the lowest byte of the last relay node's ID).
   Pre-PR-45 SQLite files are upgraded in place via ``ALTER TABLE`` so
   existing fleet members do not lose packet history on update.
"""

from __future__ import annotations

import asyncio
import sqlite3
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from src.storage.database import DatabaseManager


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


class TestCrossProtocolNameCleanup(unittest.TestCase):
    """In-memory tests of the contamination repair migration."""

    def _connect_with_seed(self, seed_rows):
        """Connect a fresh in-memory DB and insert seed rows AFTER the schema is
        created but BEFORE the migration runs. Done by calling connect() once
        to materialize the schema, inserting the seeds, then re-running the
        cleanup directly.
        """
        db = DatabaseManager(":memory:")
        _run(db.connect())
        now = datetime.now(timezone.utc).isoformat()
        for row in seed_rows:
            _run(db.execute(
                "INSERT INTO nodes (node_id, long_name, short_name, protocol, "
                "last_heard, first_seen) VALUES (?, ?, ?, ?, ?, ?)",
                (row["node_id"], row.get("long_name"), row.get("short_name"),
                 row["protocol"], now, now),
            ))
        _run(db.commit())
        return db

    def _select(self, db, node_id):
        cursor = _run(db.execute(
            "SELECT node_id, long_name, short_name, protocol FROM nodes "
            "WHERE node_id = ?",
            (node_id,),
        ))
        row = _run(cursor.fetchone())
        return dict(row) if row else None

    def test_cleans_meshtastic_row_poisoned_by_meshcore_name(self):
        """Classic bug case: MT node had its long_name overwritten with a
        MeshCore contact name. Migration should NULL the MT row."""
        db = self._connect_with_seed([
            {"node_id": "7d8b98a9", "long_name": "Guzii_RedV4",
             "short_name": "K", "protocol": "meshtastic"},
            {"node_id": "mc:Guzii_RedV4", "long_name": "Guzii_RedV4",
             "protocol": "meshcore"},
        ])

        _run(db._cleanup_cross_protocol_name_contamination())
        _run(db.commit())

        row = self._select(db, "7d8b98a9")
        self.assertIsNone(row["long_name"])
        self.assertEqual(row["short_name"], "K")

        mc_row = self._select(db, "mc:Guzii_RedV4")
        self.assertEqual(mc_row["long_name"], "Guzii_RedV4")

        _run(db.disconnect())

    def test_idempotent_when_data_clean(self):
        """No MT rows match any mc:% long_name. Migration is a no-op."""
        db = self._connect_with_seed([
            {"node_id": "deadbeef", "long_name": "Meshpoint",
             "short_name": "MPNT", "protocol": "meshtastic"},
            {"node_id": "mc:Guzii_RedV4", "long_name": "Guzii_RedV4",
             "protocol": "meshcore"},
        ])

        _run(db._cleanup_cross_protocol_name_contamination())
        _run(db.commit())

        row = self._select(db, "deadbeef")
        self.assertEqual(row["long_name"], "Meshpoint")
        self.assertEqual(row["short_name"], "MPNT")

        _run(db.disconnect())

    def test_only_touches_meshtastic_rows(self):
        """A MeshCore row that happens to share a long_name with another
        mc:% row must NOT be cleared. The migration's protocol filter
        keeps it scoped strictly to Meshtastic."""
        db = self._connect_with_seed([
            {"node_id": "mc:abc123", "long_name": "Shared Name",
             "protocol": "meshcore"},
            {"node_id": "mc:Shared Name", "long_name": "Shared Name",
             "protocol": "meshcore"},
        ])

        _run(db._cleanup_cross_protocol_name_contamination())
        _run(db.commit())

        for nid in ("mc:abc123", "mc:Shared Name"):
            row = self._select(db, nid)
            self.assertEqual(row["long_name"], "Shared Name")

        _run(db.disconnect())

    def test_skips_when_no_mc_contacts_exist(self):
        """A fresh-install DB without any mc:% rows runs cleanly."""
        db = self._connect_with_seed([
            {"node_id": "deadbeef", "long_name": "Meshpoint",
             "short_name": "MPNT", "protocol": "meshtastic"},
            {"node_id": "557673f2", "long_name": "Some MT Node",
             "protocol": "meshtastic"},
        ])

        _run(db._cleanup_cross_protocol_name_contamination())
        _run(db.commit())

        row = self._select(db, "deadbeef")
        self.assertEqual(row["long_name"], "Meshpoint")

        _run(db.disconnect())

    def test_runs_during_connect(self):
        """The cleanup must be wired into ``_run_migrations`` so a normal
        ``connect()`` call repairs poisoned rows without explicit invocation.
        """
        import tempfile
        import os

        fd, db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        try:
            db = DatabaseManager(db_path)
            _run(db.connect())
            now = datetime.now(timezone.utc).isoformat()
            _run(db.execute(
                "INSERT INTO nodes (node_id, long_name, short_name, protocol, "
                "last_heard, first_seen) VALUES "
                "('7d8b98a9', 'Guzii_RedV4', 'K', 'meshtastic', ?, ?), "
                "('mc:Guzii_RedV4', 'Guzii_RedV4', NULL, 'meshcore', ?, ?)",
                (now, now, now, now),
            ))
            _run(db.commit())
            _run(db.disconnect())

            db2 = DatabaseManager(db_path)
            _run(db2.connect())

            row = self._select(db2, "7d8b98a9")
            self.assertIsNotNone(row)
            self.assertIsNone(row["long_name"])
            self.assertEqual(row["short_name"], "K")
            self.assertEqual(row["protocol"], "meshtastic")

            _run(db2.disconnect())
        finally:
            os.unlink(db_path)


class TestRelayNodeMigration(unittest.TestCase):
    """Validate the ``packets.relay_node`` ALTER TABLE migration.

    Each test uses a tempfile-backed SQLite database so the schema state
    survives the disconnect/reconnect cycle that exercises the migration.
    """

    _OLD_PACKETS_SCHEMA = """
        CREATE TABLE packets (
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
    """

    def setUp(self):
        self._tmp_dir = tempfile.mkdtemp(prefix="meshpoint_migration_test_")
        self._db_path = str(Path(self._tmp_dir) / "test.db")

    def tearDown(self):
        import shutil
        shutil.rmtree(self._tmp_dir, ignore_errors=True)

    def _columns(self, table: str) -> set[str]:
        conn = sqlite3.connect(self._db_path)
        try:
            rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
            return {row[1] for row in rows}
        finally:
            conn.close()

    def _seed_pre_pr45_database(self) -> None:
        """Create a packets table without ``relay_node``, mirroring what a
        pre-PR-45 fleet member's SQLite file looks like on disk."""
        conn = sqlite3.connect(self._db_path)
        try:
            conn.executescript(self._OLD_PACKETS_SCHEMA)
            conn.commit()
        finally:
            conn.close()

    def test_fresh_install_has_relay_node_column(self):
        """A first-time ``connect()`` writes the canonical schema, which
        already includes the ``relay_node`` column. The migration check
        finds it and is a no-op."""
        db = DatabaseManager(self._db_path)
        _run(db.connect())
        try:
            self.assertIn("relay_node", self._columns("packets"))
        finally:
            _run(db.disconnect())

    def test_legacy_database_gets_column_added(self):
        """A pre-PR-45 SQLite file lacking the column is upgraded via
        ``ALTER TABLE`` on the next ``connect()``. Existing rows survive."""
        self._seed_pre_pr45_database()
        self.assertNotIn("relay_node", self._columns("packets"))

        db = DatabaseManager(self._db_path)
        _run(db.connect())
        try:
            self.assertIn("relay_node", self._columns("packets"))
        finally:
            _run(db.disconnect())

    def test_migration_is_idempotent_across_restarts(self):
        """A second ``connect()`` on a database that already has the column
        must not raise, must not duplicate the column, and must not lose
        existing data."""
        db1 = DatabaseManager(self._db_path)
        _run(db1.connect())
        now = datetime.now(timezone.utc).isoformat()
        _run(db1.execute(
            "INSERT INTO packets (packet_id, source_id, destination_id, "
            "protocol, packet_type, relay_node, timestamp) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("abcd1234", "deadbeef", "ffffffff", "meshtastic",
             "TEXT_MESSAGE", 0x42, now),
        ))
        _run(db1.commit())
        _run(db1.disconnect())

        db2 = DatabaseManager(self._db_path)
        _run(db2.connect())
        try:
            cols = self._columns("packets")
            self.assertEqual(
                sum(1 for c in cols if c == "relay_node"), 1,
                "relay_node column duplicated on second connect()",
            )

            cursor = _run(db2.execute(
                "SELECT relay_node FROM packets WHERE packet_id = ?",
                ("abcd1234",),
            ))
            row = _run(cursor.fetchone())
            self.assertIsNotNone(row)
            self.assertEqual(row["relay_node"], 0x42)
        finally:
            _run(db2.disconnect())

    def test_legacy_row_defaults_relay_node_to_zero(self):
        """Rows inserted into the pre-PR-45 schema must read back with
        ``relay_node = 0`` after the column is added (the ALTER TABLE
        default value applies retroactively to existing rows)."""
        self._seed_pre_pr45_database()
        now = datetime.now(timezone.utc).isoformat()

        conn = sqlite3.connect(self._db_path)
        try:
            conn.execute(
                "INSERT INTO packets (packet_id, source_id, destination_id, "
                "protocol, packet_type, timestamp) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                ("legacy01", "11111111", "ffffffff", "meshtastic",
                 "TEXT_MESSAGE", now),
            )
            conn.commit()
        finally:
            conn.close()

        db = DatabaseManager(self._db_path)
        _run(db.connect())
        try:
            cursor = _run(db.execute(
                "SELECT relay_node FROM packets WHERE packet_id = ?",
                ("legacy01",),
            ))
            row = _run(cursor.fetchone())
            self.assertIsNotNone(row)
            self.assertEqual(row["relay_node"], 0)
        finally:
            _run(db.disconnect())


if __name__ == "__main__":
    unittest.main()
