from __future__ import annotations

import logging
from src.models.node import Node
from src.storage.node_repository import NodeRepository

logger = logging.getLogger(__name__)


class NetworkMapper:
    """Builds and queries the network topology from discovered nodes."""

    def __init__(self, node_repo: NodeRepository):
        self._node_repo = node_repo

    async def get_all_nodes(self) -> list[Node]:
        return await self._node_repo.get_all()

    async def get_nodes_with_position(self) -> list[Node]:
        return await self._node_repo.get_with_position()

    async def get_node_count(self) -> int:
        return await self._node_repo.get_count()

    async def get_network_summary(self) -> dict:
        all_nodes = await self._node_repo.get_all()
        positioned = [n for n in all_nodes if n.has_position]

        protocols: dict[str, int] = {}
        for node in all_nodes:
            protocols[node.protocol] = protocols.get(node.protocol, 0) + 1

        total_packets = sum(n.packet_count for n in all_nodes)

        return {
            "total_nodes": len(all_nodes),
            "nodes_with_position": len(positioned),
            "total_packets_seen": total_packets,
            "protocols": protocols,
        }

    async def get_map_data(self) -> list[dict]:
        """Return nodes formatted for the Leaflet map layer."""
        nodes = await self._node_repo.get_with_position()
        return [
            {
                "node_id": n.node_id,
                "display_name": n.display_name,
                "latitude": n.latitude,
                "longitude": n.longitude,
                "altitude": n.altitude,
                "protocol": n.protocol,
                "packet_count": n.packet_count,
                "last_heard": n.last_heard.isoformat(),
                "signal": n.latest_signal.to_dict() if n.latest_signal else None,
            }
            for n in nodes
        ]
