"""Regional starting points, not equipment approval or regulatory certification.

Sources and limitations are documented in docs/RETICULUM-REGIONS.md.
Never reuse core Meshtastic RF settings: this is a separate radio network.
"""
RADIO_KEYS = (
    "rnode_frequency_hz", "rnode_bandwidth_hz", "rnode_tx_power",
    "rnode_spreading_factor", "rnode_coding_rate",
    "rnode_airtime_limit_short", "rnode_airtime_limit_long",
)

# Centers leave room for the entire nominal channel inside the selected band.
# These are Meshpoint starting profiles, not nationwide Reticulum channels.
PROFILES = {
    "US": (915_000_000, 500_000),
    "EU_868": (869_525_000, 125_000),
    "ANZ": (916_000_000, 500_000),
    "IN": (866_000_000, 125_000),
    "KR": (921_900_000, 125_000),
    "SG_923": (923_000_000, 125_000),
}


def defaults(region):
    profile = PROFILES.get(str(region).upper())
    if profile is None:
        return {}
    return dict(zip(RADIO_KEYS, (*profile, 7, 7, 5, 10.0, 1.0)))


def describe(region):
    region = str(region or "UNKNOWN").upper()
    return {
        "radio_region": region,
        "radio_defaults": defaults(region),
        "radio_profile_available": region in PROFILES,
        "radio_note": "Starting profile only. Match your peer and verify local band, antenna, equipment and access requirements. Existing manual settings are preserved.",
    }
