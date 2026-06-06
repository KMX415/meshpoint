"""LoRa time-on-air estimates for RX traffic analytics.

Shared by the 24-hour traffic histogram (PR 2) and future duty-cycle
work (PR 7). Uses the same fallback formula as ``TxService._estimate_airtime``
so dashboard estimates stay consistent with TX budgeting when HAL ToA
is unavailable.
"""

from __future__ import annotations

DEFAULT_PAYLOAD_BYTES = 40
MIN_PAYLOAD_BYTES = 20


def estimate_toa_ms(
    spreading_factor: int,
    bandwidth_khz: float,
    *,
    preamble_length: int = 16,
    payload_bytes: int = DEFAULT_PAYLOAD_BYTES,
) -> int:
    """Rough airtime per packet in milliseconds.

    Args:
        spreading_factor: LoRa SF (7–12 typical).
        bandwidth_khz: Channel bandwidth in kHz.
        preamble_length: Preamble symbol count from radio config.
        payload_bytes: Payload size used for the symbol estimate.
    """
    if spreading_factor <= 0 or bandwidth_khz <= 0:
        return 0

    payload = max(MIN_PAYLOAD_BYTES, int(payload_bytes))
    symbol_time_ms = (2 ** spreading_factor) / bandwidth_khz
    n_symbols = 8 + max(
        (
            (8 * payload - 4 * spreading_factor + 28 + 16)
            // (4 * spreading_factor)
        )
        * 5
        + 8,
        0,
    )
    return int((preamble_length + n_symbols) * symbol_time_ms)


def estimate_packet_toa_ms(
    packet,
    *,
    default_sf: int,
    default_bw_khz: float,
    default_preamble: int = 16,
) -> int:
    """Estimate airtime for a single packet using signal metadata when present."""
    sf = default_sf
    bw = default_bw_khz
    signal = getattr(packet, "signal", None)
    if signal is not None:
        if getattr(signal, "spreading_factor", None):
            sf = int(signal.spreading_factor)
        if getattr(signal, "bandwidth_khz", None):
            bw = float(signal.bandwidth_khz)

    payload_bytes = DEFAULT_PAYLOAD_BYTES
    raw = getattr(packet, "raw_app_payload", None)
    if raw:
        payload_bytes = len(raw)
    else:
        decoded = getattr(packet, "decoded_payload", None) or {}
        text = decoded.get("text")
        if text:
            payload_bytes = len(str(text).encode("utf-8"))

    return estimate_toa_ms(
        sf,
        bw,
        preamble_length=default_preamble,
        payload_bytes=payload_bytes,
    )


def sum_hourly_toa_ms(
    buckets: list[dict],
    *,
    default_sf: int,
    default_bw_khz: float,
    default_preamble: int = 16,
    default_payload_bytes: int = DEFAULT_PAYLOAD_BYTES,
) -> int:
    """Sum estimated airtime for modem-grouped hourly buckets."""
    total = 0
    for row in buckets:
        sf = int(row.get("sf") or default_sf)
        bw = float(row.get("bw") or default_bw_khz)
        count = int(row.get("packet_count") or 0)
        payload = int(row.get("avg_payload") or default_payload_bytes)
        total += count * estimate_toa_ms(
            sf,
            bw,
            preamble_length=default_preamble,
            payload_bytes=payload,
        )
    return total
