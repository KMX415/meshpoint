"""Topology graph aggregation from NEIGHBORINFO and TRACEROUTE packets."""

from __future__ import annotations

import json
import unittest
from datetime import datetime, timedelta, timezone

from src.storage.database import DatabaseManager
from src.storage.packet_repository import PacketRepository


class TestTopologyGraph(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.db = DatabaseManager(":memory:")
        await self.db.connect()
        self.repo = PacketRepository(self.db)

    async def asyncTearDown(self):
        await self.db.disconnect()

    async def _insert_neighborinfo(
        self,
        packet_id: str,
        source_id: str,
        neighbors: list[dict],
        *,
        rssi: float = -95.0,
        ts: datetime | None = None,
    ) -> None:
        ts = ts or datetime.now(timezone.utc)
        payload = json.dumps({"neighbors": neighbors})
        await self.db.execute(
            """
            INSERT INTO packets (
                packet_id, source_id, destination_id, protocol,
                packet_type, hop_limit, hop_start, channel_hash,
                want_ack, via_mqtt, relay_node, decoded_payload, decrypted,
                rssi, snr, frequency_mhz, spreading_factor,
                bandwidth_khz, capture_source, timestamp
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                packet_id, source_id, "ffffffff", "meshtastic", "neighborinfo",
                3, 3, 8, 0, 0, 0, payload, 1,
                rssi, 5.0, 906.875, 11, 250, "concentrator", ts.isoformat(),
            ),
        )

    async def _insert_routing(
        self,
        packet_id: str,
        source_id: str,
        route_reply: list[str],
    ) -> None:
        payload = json.dumps({"route_reply": route_reply})
        ts = datetime.now(timezone.utc).isoformat()
        await self.db.execute(
            """
            INSERT INTO packets (
                packet_id, source_id, destination_id, protocol,
                packet_type, hop_limit, hop_start, channel_hash,
                want_ack, via_mqtt, relay_node, decoded_payload, decrypted,
                rssi, snr, frequency_mhz, spreading_factor,
                bandwidth_khz, capture_source, timestamp
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                packet_id, source_id, "ffffffff", "meshtastic", "routing",
                3, 3, 8, 0, 0, 0, payload, 1,
                -92.0, 6.0, 906.875, 11, 250, "concentrator", ts,
            ),
        )

    async def _insert_traceroute(
        self,
        packet_id: str,
        source_id: str,
        route: list[str],
    ) -> None:
        payload = json.dumps({"route": route})
        ts = datetime.now(timezone.utc).isoformat()
        await self.db.execute(
            """
            INSERT INTO packets (
                packet_id, source_id, destination_id, protocol,
                packet_type, hop_limit, hop_start, channel_hash,
                want_ack, via_mqtt, relay_node, decoded_payload, decrypted,
                rssi, snr, frequency_mhz, spreading_factor,
                bandwidth_khz, capture_source, timestamp
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                packet_id, source_id, "ffffffff", "meshtastic", "traceroute",
                3, 3, 8, 0, 0, 0, payload, 1,
                -90.0, 5.0, 906.875, 11, 250, "concentrator", ts,
            ),
        )

    async def test_neighborinfo_edges_and_weak_flag(self):
        await self._insert_neighborinfo(
            "ni1", "aaaa0001",
            [{"node_id": "bbbb0002", "snr": 4.5}],
            rssi=-115.0,
        )
        await self._insert_neighborinfo(
            "ni2", "cccc0003",
            [{"node_id": "dddd0004", "snr": 8.0}],
            rssi=-88.0,
        )
        await self.db.commit()

        graph = await self.repo.get_topology_graph(24)
        self.assertEqual(len(graph["edges"]), 2)
        weak = [e for e in graph["edges"] if e["weak"]]
        strong = [e for e in graph["edges"] if not e["weak"]]
        self.assertEqual(len(weak), 1)
        self.assertEqual(len(strong), 1)
        self.assertEqual(weak[0]["rssi"], -115.0)

    async def test_hours_window_excludes_old_packets(self):
        old = datetime.now(timezone.utc) - timedelta(hours=30)
        await self._insert_neighborinfo(
            "old", "aaaa0001",
            [{"node_id": "bbbb0002", "snr": 1.0}],
            ts=old,
        )
        await self.db.commit()

        graph = await self.repo.get_topology_graph(24)
        self.assertEqual(graph["edges"], [])

    async def test_traceroute_paths_included(self):
        await self._insert_neighborinfo(
            "ni", "aaaa0001", [{"node_id": "bbbb0002", "snr": 3.0}],
        )
        await self._insert_traceroute(
            "tr", "aaaa0001", ["aaaa0001", "bbbb0002", "cccc0003"],
        )
        await self.db.commit()

        graph = await self.repo.get_topology_graph(24)
        self.assertEqual(len(graph["routes"]), 1)
        self.assertEqual(graph["routes"][0]["route"][1], "bbbb0002")
        node_ids = {n["id"] for n in graph["nodes"]}
        self.assertIn("cccc0003", node_ids)

    async def test_traceroute_hops_become_edges(self):
        await self._insert_traceroute(
            "tr", "aaaa0001", ["aaaa0001", "bbbb0002", "cccc0003"],
        )
        await self.db.commit()

        graph = await self.repo.get_topology_graph(24)
        self.assertEqual(len(graph["edges"]), 2)
        types = {e["edge_type"] for e in graph["edges"]}
        self.assertEqual(types, {"traceroute"})
        self.assertIn("traceroute", graph["edge_sources"])

    async def test_routing_route_reply_becomes_edges(self):
        await self._insert_routing(
            "rt", "dddd0005",
            ["dddd0005", "eeee0006", "ffff0007"],
        )
        await self.db.commit()

        graph = await self.repo.get_topology_graph(24)
        self.assertEqual(len(graph["edges"]), 2)
        self.assertTrue(all(e["edge_type"] == "routing" for e in graph["edges"]))
        self.assertIn("routing", graph["edge_sources"])

    async def test_neighborinfo_wins_over_traceroute_for_same_link(self):
        await self._insert_traceroute(
            "tr", "aaaa0001", ["aaaa0001", "bbbb0002"],
        )
        await self._insert_neighborinfo(
            "ni", "aaaa0001", [{"node_id": "bbbb0002", "snr": 4.0}],
        )
        await self.db.commit()

        graph = await self.repo.get_topology_graph(24)
        self.assertEqual(len(graph["edges"]), 1)
        self.assertEqual(graph["edges"][0]["edge_type"], "neighborinfo")
        self.assertEqual(graph["edges"][0]["confidence"], "high")

    async def test_normalize_node_id_formats(self):
        self.assertEqual(PacketRepository._normalize_node_id("!AABB0001"), "aabb0001")
        self.assertEqual(PacketRepository._normalize_node_id("aa1"), "00000aa1")


if __name__ == "__main__":
    unittest.main()
