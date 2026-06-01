"""Meshtastic reply hop limits (mirrors firmware RoutingModule::getHopLimitForResponse)."""

from __future__ import annotations


class MeshtasticReplyHopPolicy:
    """Compute outbound hop fields for want_response replies."""

    @staticmethod
    def hops_away(
        hop_limit: int,
        hop_start: int,
        *,
        default_if_unknown: int = -1,
    ) -> int:
        """Return hops consumed, or default_if_unknown when header fields are invalid."""
        if hop_start < hop_limit:
            return default_if_unknown
        return hop_start - hop_limit

    @classmethod
    def hop_limit_for_response(
        cls,
        hop_limit: int,
        hop_start: int,
        configured_hop_limit: int,
    ) -> int:
        """Mirror Meshtastic firmware getHopLimitForResponse for decoded packets."""
        hops_used = cls.hops_away(hop_limit, hop_start)
        if hops_used >= 0:
            if hops_used > configured_hop_limit:
                return hops_used
            if hop_start == 0:
                return 0
            if hops_used + 2 < configured_hop_limit:
                return hops_used + 2
        return configured_hop_limit

    @classmethod
    def reply_hop_fields(
        cls,
        hop_limit: int,
        hop_start: int,
        configured_hop_limit: int,
    ) -> tuple[int, int]:
        """Return (hop_limit, hop_start) for a unicast reply packet."""
        reply_limit = cls.hop_limit_for_response(
            hop_limit, hop_start, configured_hop_limit
        )
        return reply_limit, reply_limit
