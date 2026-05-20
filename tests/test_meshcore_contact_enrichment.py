from __future__ import annotations

import asyncio
import unittest

from src.api.meshcore_contacts import sync_meshcore_contacts_to_nodes
from src.models.node import Node
from src.storage.database import DatabaseManager
from src.storage.node_repository import NodeRepository


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


class _Coord:
    def __init__(self, repo: NodeRepository):
        self.node_repo = repo


class _MeshCoreTx:
    connected = True

    def __init__(self, contacts):
        self._contacts = contacts

    async def get_contacts(self):
        return self._contacts


class TestMeshCoreContactEnrichment(unittest.TestCase):
    def setUp(self) -> None:
        self.db = DatabaseManager(":memory:")
        _run(self.db.connect())
        self.repo = NodeRepository(self.db)
        self.coord = _Coord(self.repo)

    def tearDown(self) -> None:
        _run(self.db.disconnect())

    def test_contact_name_updates_matching_meshcore_node(self):
        _run(self.repo.upsert(Node(
            node_id="e34ef4172778",
            protocol="meshcore",
        )))

        updated = _run(sync_meshcore_contacts_to_nodes(
            self.coord,
            _MeshCoreTx([{
                "public_key": "e34ef4172778aaaabbbbcccc",
                "name": "Ridge Repeater",
            }]),
        ))

        node = _run(self.repo.get_by_id("e34ef4172778"))
        self.assertEqual(updated, 1)
        self.assertEqual(node.long_name, "Ridge Repeater")
        self.assertEqual(node.short_name, "Ridg")
        self.assertEqual(node.display_name, "Ridge Repeater")

    def test_sync_applies_all_contacts_not_only_triggering_packet(self):
        _run(self.repo.upsert(Node(
            node_id="e34ef4172778",
            protocol="meshcore",
        )))
        _run(self.repo.upsert(Node(
            node_id="c1871770ebc1",
            protocol="meshcore",
        )))

        updated = _run(sync_meshcore_contacts_to_nodes(
            self.coord,
            _MeshCoreTx([
                {
                    "public_key": "e34ef4172778aaaabbbbcccc",
                    "name": "Ridge Repeater",
                },
                {
                    "public_key": "c1871770ebc1deadbeef",
                    "name": "Valley Node",
                },
            ]),
        ))

        self.assertEqual(updated, 2)
        ridge = _run(self.repo.get_by_id("e34ef4172778"))
        valley = _run(self.repo.get_by_id("c1871770ebc1"))
        self.assertEqual(ridge.long_name, "Ridge Repeater")
        self.assertEqual(valley.long_name, "Valley Node")


if __name__ == "__main__":
    unittest.main()
