"""Gateway vs WisMesh Node platform boundaries.

Gateway installs use the SX1302 concentrator stack (capture, native TX,
PKI mesh participant, spectral scan). Node installs delegate RF to
meshtasticd on the RAK6421 HAT; Meshpoint is observability + dashboard
only on that path.

When merging ``main`` into ``feat/wismesh-hat``, any new gateway feature
must either gate on :func:`is_gateway_platform` or be safe on node
(meshtasticd API path). See ``docs/plans/wismesh-branch-merge.md`` and
``tests/test_node_platform_invariants.py``.
"""

from __future__ import annotations

from src.config import AppConfig

PLATFORM_GATEWAY = "gateway"
PLATFORM_NODE = "node"

# Registry enforced by tests/test_node_platform_invariants.py
GATEWAY_ONLY_CAPABILITIES: tuple[str, ...] = (
    "pki_keypair_bootstrap",
    "pki_public_key_hydration",
    "inbound_mesh_participant_replies",
    "telemetry_broadcaster",
    "position_broadcaster",
    "tx_gain_injection",
    "native_sx1302_relay",
    "spectral_scan",
    "concentrator_dangerous_action",
)


def is_node_platform(config: AppConfig) -> bool:
    return config.device.platform == PLATFORM_NODE


def is_gateway_platform(config: AppConfig) -> bool:
    return not is_node_platform(config)
