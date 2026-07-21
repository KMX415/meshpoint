"""Meshtastic channel-to-frequency resolution for serial capture.

Replicates the frequency computation in meshtastic firmware
``RadioInterface::applyModemConfig`` so USB-stick packets can carry
the stick's real center frequency instead of a hardcoded guess.

Only PROFILE_STD / PROFILE_EU868 regions (spacing=0, padding=0) are
modelled: the same set already used elsewhere in this codebase.
Unsupported regions resolve to 0.0 rather than a wrong number.

Credit: javastraat/meshpoint ``77cdaa2`` + ``dc3fc0a``.
"""

from __future__ import annotations

from typing import Optional

# (freqStart, freqEnd) in MHz from firmware regions[] (spacing=0, padding=0).
_REGION_BAND_MHZ: dict[str, tuple[float, float]] = {
    "US": (902.0, 928.0),
    "EU_433": (433.0, 434.0),
    "EU_868": (869.4, 869.65),
    "ANZ": (915.0, 928.0),
    "IN": (865.0, 867.0),
    "KR": (920.0, 923.0),
    "SG_923": (917.0, 925.0),
}

# Firmware DisplayFormatters::getModemPresetDisplayName (useShortName=false).
# Kept separate from src.radio.presets UI labels (e.g. LONG_MODERATE -> LongMod).
_PRESET_HASH_NAME: dict[str, str] = {
    "SHORT_TURBO": "ShortTurbo",
    "SHORT_SLOW": "ShortSlow",
    "SHORT_FAST": "ShortFast",
    "MEDIUM_SLOW": "MediumSlow",
    "MEDIUM_FAST": "MediumFast",
    "LONG_SLOW": "LongSlow",
    "LONG_FAST": "LongFast",
    "LONG_TURBO": "LongTurbo",
    "LONG_MODERATE": "LongMod",
    "LITE_FAST": "LiteFast",
    "LITE_SLOW": "LiteSlow",
    "NARROW_FAST": "NarrowFast",
    "NARROW_SLOW": "NarrowSlow",
    "TINY_FAST": "TinyFast",
    "TINY_SLOW": "TinySlow",
}
_PRESET_HASH_NAME_FALLBACK = "Invalid"
_CUSTOM_HASH_NAME = "Custom"


def _djb2(text: str) -> int:
    """djb2 matching firmware ``hash()``: seed 5381, uint32 wrap."""
    h = 5381
    for byte in text.encode("utf-8"):
        h = ((h << 5) + h + byte) & 0xFFFFFFFF
    return h


def _preset_hash_name(modem_preset: Optional[str], use_preset: bool) -> str:
    if not use_preset:
        return _CUSTOM_HASH_NAME
    return _PRESET_HASH_NAME.get(modem_preset or "", _PRESET_HASH_NAME_FALLBACK)


def resolve_frequency_mhz(
    *,
    region: Optional[str],
    channel_num: Optional[int],
    bandwidth_khz: Optional[float],
    channel_name: Optional[str] = None,
    modem_preset: Optional[str] = None,
    use_preset: bool = True,
    frequency_offset: float = 0.0,
    override_frequency: float = 0.0,
) -> float:
    """Operating frequency matching firmware slot selection.

    ``channel_num`` 0 means hash-derived slot; positive N is explicit
    1-based slot N. Returns 0.0 when there is not enough information.
    """
    if override_frequency:
        return round(override_frequency + frequency_offset, 4)

    if not region or not bandwidth_khz:
        return 0.0
    band = _REGION_BAND_MHZ.get(region)
    if band is None:
        return 0.0

    freq_start, freq_end = band
    freq_slot_width = bandwidth_khz / 1000.0
    if freq_slot_width <= 0:
        return 0.0
    num_slots = round((freq_end - freq_start) / freq_slot_width)
    if num_slots <= 0:
        return 0.0

    if channel_num:
        slot = channel_num - 1
        if slot >= num_slots:
            return 0.0
    else:
        name = (channel_name or "").strip()
        if not name:
            name = _preset_hash_name(modem_preset, use_preset)
        slot = _djb2(name) % num_slots

    freq = freq_start + (bandwidth_khz / 2000.0) + slot * freq_slot_width
    return round(freq + frequency_offset, 4)
