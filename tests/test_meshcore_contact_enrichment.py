from __future__ import annotations

import asyncio
import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from src.analytics.stats_reporter import StatsReporter
from src.api.meshcore_contacts import sync_meshcore_contacts_to_nodes
from src.api.upstream_client import UpstreamClient
from src.config import AppConfig, UpstreamConfig
from src.coordinator import PipelineCoordinator
from src.decode.meshcore_event_adapter import adapt_event
from src.models.device_identity import DeviceIdentity
from src.models.node import Node
from src.storage.database import DatabaseManager
from src.storage.node_repository import NodeRepository
from src.transmit.meshcore_contacts import MeshcoreContactParser


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


class _Coord:
    def __init__(self, repo: NodeRepository):
        self.node_repo = repo
        self.stats_reporter = StatsReporter()


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

    def test_short_prefix_collision_does_not_contaminate(self):
        # Two nodes share the first 8 hex chars; only the exact 12-char
        # match may receive the contact name.
        _run(self.repo.upsert(Node(
            node_id="e34ef4172778",
            protocol="meshcore",
        )))
        _run(self.repo.upsert(Node(
            node_id="e34ef4179999",
            protocol="meshcore",
            long_name="Keep Me",
        )))

        updated = _run(sync_meshcore_contacts_to_nodes(
            self.coord,
            _MeshCoreTx([{
                "public_key": "e34ef4172778aaaabbbbcccc",
                "name": "Ridge Repeater",
            }]),
        ))

        self.assertEqual(updated, 1)
        matched = _run(self.repo.get_by_id("e34ef4172778"))
        other = _run(self.repo.get_by_id("e34ef4179999"))
        self.assertEqual(matched.long_name, "Ridge Repeater")
        self.assertEqual(other.long_name, "Keep Me")

    def test_key_only_advert_enriches_local_map_and_cloud_heartbeat(self):
        public_key = "aabb00112233" + "44" * 26
        packet = adapt_event(json.dumps({
            "event_type": "advertisement", "payload": {"public_key": public_key},
        }).encode())
        self.assertNotIn("latitude", packet.decoded_payload)
        pipeline = PipelineCoordinator(AppConfig())
        pipeline._node_repo = self.repo
        pipeline._stats_reporter = self.coord.stats_reporter
        _run(pipeline._update_node(packet))
        before = _run(self.repo.get_by_id(public_key[:12]))

        result = SimpleNamespace(payload={public_key: {
            "public_key": public_key, "adv_name": "Ridge Repeater",
            "adv_lat": 43.9091, "adv_lon": -72.2207,
        }})
        with patch.object(MeshcoreContactParser, "_is_error_event", return_value=False):
            contacts = MeshcoreContactParser.from_command_result(result)
        self.assertEqual(_run(sync_meshcore_contacts_to_nodes(
            self.coord, _MeshCoreTx(contacts),
        )), 1)
        positioned = _run(self.repo.get_with_position())
        self.assertEqual(len(positioned), 1)
        node = positioned[0]
        self.assertEqual((node.latitude, node.longitude), (43.9091, -72.2207))
        self.assertEqual(node.last_heard, before.last_heard)
        self.assertEqual(node.packet_count, before.packet_count)
        self.assertEqual(self.coord.stats_reporter.total_packets, 0)

        client = UpstreamClient(UpstreamConfig(), DeviceIdentity(device_id="test-device"),
                                stats_reporter=self.coord.stats_reporter)
        def assert_heartbeat_position():
            roster = client._build_heartbeat()["nodes"]
            self.assertEqual(len(roster), 1)
            self.assertEqual(roster[0]["source_id"], public_key[:12])
            self.assertEqual(roster[0]["protocol"], "meshcore")
            self.assertEqual(roster[0]["decoded_payload"]["latitude"], 43.9091)
            self.assertEqual(roster[0]["decoded_payload"]["longitude"], -72.2207)
            self.assertEqual(roster[0]["decoded_payload"]["long_name"], "Ridge Repeater")

        assert_heartbeat_position()
        # Another incomplete advert must not wipe the queued position/name.
        _run(pipeline._update_node(packet))
        assert_heartbeat_position()
        self.coord.stats_reporter.reset()
        # Nor should it lose persisted metadata after the previous heartbeat.
        _run(pipeline._update_node(packet))
        assert_heartbeat_position()

    def test_unchanged_contacts_do_not_queue_another_node_update(self):
        _run(self.repo.upsert(Node(node_id="aabb00112233", protocol="meshcore")))
        tx = _MeshCoreTx([{
            "public_key": "aabb001122334455", "name": "Ridge",
            "adv_lat": 10, "adv_lon": 20,
        }])
        self.assertEqual(_run(sync_meshcore_contacts_to_nodes(self.coord, tx)), 1)
        self.coord.stats_reporter.reset()
        self.assertEqual(_run(sync_meshcore_contacts_to_nodes(self.coord, tx)), 0)
        self.assertEqual(self.coord.stats_reporter.build_node_roster(), [])

    def test_position_does_not_require_a_friendly_name(self):
        for name, lat, lon in [("", 0, 20), ("aabb00112233", 10, 0)]:
            with self.subTest(name=name):
                _run(self.repo.upsert(Node(
                    node_id="aabb00112233", protocol="meshcore", long_name="Keep Name",
                    short_name="Mine",
                )))
                self.assertEqual(_run(sync_meshcore_contacts_to_nodes(self.coord, _MeshCoreTx([{
                    "public_key": "aabb001122334455", "name": name,
                    "adv_lat": lat, "adv_lon": lon,
                }]))), 1)
                node = _run(self.repo.get_by_id("aabb00112233"))
                self.assertEqual((node.latitude, node.longitude), (lat, lon))
                self.assertEqual((node.long_name, node.short_name), ("Keep Name", "Mine"))

    def test_invalid_position_preserves_existing_pair_while_name_updates(self):
        for lat, lon in [(None, 20), (10, None), (0, 0), (91, 20), (10, float("nan"))]:
            with self.subTest(lat=lat, lon=lon):
                _run(self.repo.upsert(Node(
                    node_id="aabb00112233", protocol="meshcore", latitude=30, longitude=40,
                )))
                _run(sync_meshcore_contacts_to_nodes(self.coord, _MeshCoreTx([{
                    "public_key": "aabb001122334455", "name": "Ridge",
                    "adv_lat": lat, "adv_lon": lon,
                }])))
                node = _run(self.repo.get_by_id("aabb00112233"))
                self.assertEqual((node.latitude, node.longitude), (30, 40))
                self.assertEqual(node.long_name, "Ridge")

    def test_contact_positions_only_update_exact_heard_meshcore_nodes(self):
        for node_id, protocol in [("aabb00112233", "meshcore"),
                                  ("aabb00119999", "meshcore"),
                                  ("ccdd00112233", "meshtastic")]:
            _run(self.repo.upsert(Node(node_id=node_id, protocol=protocol)))
        contacts = [{"public_key": pk, "name": "Ridge", "adv_lat": 10, "adv_lon": 20}
                    for pk in ("AABB001122334455", "ccdd001122334455", "eeee001122334455")]
        self.assertEqual(_run(sync_meshcore_contacts_to_nodes(self.coord, _MeshCoreTx(contacts))), 1)
        self.assertEqual(_run(self.repo.get_count()), 3)
        self.assertIsNone(_run(self.repo.get_by_id("aabb00119999")).latitude)
        self.assertIsNone(_run(self.repo.get_by_id("ccdd00112233")).latitude)


if __name__ == "__main__":
    unittest.main()
