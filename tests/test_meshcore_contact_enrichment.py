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

    async def get_contacts(self):
        return [{
            "public_key": "e34ef4172778aaaabbbbcccc",
            "name": "Ridge Repeater",
        }]


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
            _MeshCoreTx(),
            "e34ef4172778",
        ))

        node = _run(self.repo.get_by_id("e34ef4172778"))
        self.assertEqual(updated, 1)
        self.assertEqual(node.long_name, "Ridge Repeater")
        self.assertEqual(node.short_name, "Ridg")
        self.assertEqual(node.display_name, "Ridge Repeater")


if __name__ == "__main__":
    unittest.main()
