# Radio Config Explained

What each radio knob does, why it matters, and when to deviate from the
defaults. For configuration syntax and full field reference see
[Configuration > Radio](CONFIGURATION.md#radio).

If you just want a working setup that matches the public mesh, the
defaults are correct: pick your region in the setup wizard and leave
everything else alone. This document is for users who want to tune for
custom slots, narrowband experiments, or regulatory compliance.

---

## Identity (`transmit.node_id`, `transmit.long_name`, `transmit.short_name`)

**What it is.** Three fields that together make up the Meshpoint's identity
on the Meshtastic mesh. The `node_id` is the 32-bit integer other nodes use
to address packets to you (rendered as `!xxxxxxxx` in firmware UIs). The
`long_name` and `short_name` are what appears in the recipient's contact
list when your NodeInfo broadcast lands.

**Why it matters.** Meshtastic clients only thread direct messages through
contacts they know about, and they only learn about contacts via NodeInfo
packets. If your `node_id` shifts between restarts, every restart looks like
a brand new node from the recipient's point of view, and DMs sent back to
the "old" Meshpoint go nowhere. Pre-v0.6.7 Meshpoints had this exact bug;
v0.6.7 makes the identity stable.

**Resolution priority** (first match wins, evaluated at service startup):

1. `transmit.node_id` set explicitly in `config/local.yaml` (or via the
   dashboard radio tab, which writes the same field).
2. **Derived** from `device.device_id` (your provisioned UUID) using
   SHA-256, then taking the first 4 bytes as a 32-bit unsigned integer.
   Reserved values `0x00000000` and `0xFFFFFFFF` are explicitly skipped.
   This path is deterministic: the same `device_id` always produces the
   same `node_id`, so restarts are stable.
3. **Cryptographically random** fallback (`secrets.randbits(32)`) if
   neither is set. The startup log will WARN when this happens because it
   means your identity will not survive a restart.

**How to change it.** Three equivalent ways:

- **Dashboard:** Settings -> Radio -> Identity -> Save. Overwrites the
  `transmit.*` block in `local.yaml`.
- **Wizard:** `meshpoint setup` walks through identity prompts in the
  Device step and prints the resolved values before saving.
- **YAML edit:** open `config/local.yaml` in your editor and edit the
  `transmit.node_id`, `transmit.long_name`, and `transmit.short_name`
  fields directly.

**Identity changes require a service restart.** The resolved `source_node_id`
is captured once at startup and reused for the lifetime of the process, both
for outbound DMs/text and the periodic NodeInfo broadcast. After editing,
either:

```bash
sudo systemctl restart meshpoint
```

or use the **Restart** button on the dashboard Settings page. The next
NodeInfo broadcast (within 60 seconds of restart, then every 30 minutes)
will publish your new identity to the mesh.

---

## Region

The first thing the setup wizard asks. The region selects:

- **Default frequency** within the regional ISM band
- **Allowed band limits** (you cannot set `frequency_mhz` outside these)
- **MeshCore companion preset** (frequency, BW, SF, CR for that region's
  standard MeshCore channel)

Supported regions and their defaults:

| Region | Default frequency | Allowed band | Notes |
|---|---|---|---|
| `US` | 906.875 MHz | 902.0 - 928.0 MHz | FCC Part 15 (unlicensed). 500 kHz BW required for non-hopping operation. |
| `EU_868` | 869.525 MHz | 863.0 - 870.0 MHz | ETSI EN 300 220. 1% duty cycle limit. |
| `ANZ` | 919.875 MHz | 915.0 - 928.0 MHz | AS/NZS 4268. |
| `IN` | 865.875 MHz | 865.0 - 867.0 MHz | India ISM. |
| `KR` | 922.875 MHz | 920.0 - 923.0 MHz | South Korea ISM. |
| `SG_923` | 917.875 MHz | 917.0 - 925.0 MHz | Singapore ISM. |

If you set `frequency_mhz` outside the band, the service refuses to start.
Omit `frequency_mhz` entirely to use the regional default.

---

## Spreading Factor (SF)

Controls how many "chips" of the carrier are used per data symbol. Higher SF =
slower data rate but better sensitivity (longer range, more processing gain).

| SF | Symbol time @ BW250 | Relative airtime | Sensitivity |
|---|---|---|---|
| 7 | 0.512 ms | 1x (fastest) | Lowest (shortest range) |
| 8 | 1.024 ms | 2x | |
| 9 | 2.048 ms | 4x | |
| 10 | 4.096 ms | 8x | |
| 11 | 8.192 ms | 16x | |
| 12 | 16.384 ms | 32x (slowest) | Highest (longest range) |

Higher SF gives more **processing gain** at the receiver: it averages over
a longer symbol, recovering signals deeper in the noise. The cost is
airtime: an SF12 packet takes 32x longer than SF7 to transmit, eating
duty-cycle budget and increasing collision probability.

---

## Bandwidth (BW)

The width of the LoRa channel. Wider BW transmits faster but spreads the
signal across more spectrum, raising the noise floor seen by the demodulator.

| BW (kHz) | Notes |
|---|---|
| 62.5 | Used by MeshCore on most regions. **Not receivable on the SX1302 concentrator** (see note below); requires a USB companion radio |
| 125 | Narrower, slower, slightly more sensitive at the same SF |
| 250 | Meshtastic standard for most presets |
| 500 | Wider, faster, **required for non-hopping operation under FCC Part 15 in the 902-928 MHz band** |

US Part 15 is the practical reason most US Meshpoints stay on BW 250 by
default (LongFast preset) and only move to BW 500 when running a non-hopping
custom slot.

### SX1302 minimum bandwidth

The SX1302 concentrator used by every Meshpoint platform (RAK V2, SenseCap
M1, RAK2287 DIY) has a hardware floor of **125 kHz**. Anything narrower
(notably MeshCore's default 62.5 kHz) cannot be demodulated regardless of
`bandwidth_khz` setting. For sub-125 kHz signals use a
[USB companion radio](HARDWARE-MATRIX.md#meshcore-usb-companion-radios).

---

## Coding Rate (CR)

Forward error correction overhead. `4/5` adds 25% overhead, `4/8` doubles
the payload. Higher CR = better packet recovery in marginal conditions, at
the cost of throughput.

Meshtastic standard is `4/5`. Almost no reason to change.

---

## Standard Meshtastic Presets

Combinations of SF + BW that the Meshtastic firmware exposes as named
presets. The cloud and most apps assume these:

| Preset | SF | BW (kHz) | Use case |
|---|---|---|---|
| ShortTurbo | 7 | 500 | Maximum throughput, very short range |
| ShortFast | 7 | 250 | Fast, short range |
| ShortSlow | 8 | 250 | Slightly more reliable |
| MediumFast | 9 | 250 | Balanced for medium-density meshes |
| MediumSlow | 10 | 250 | More range, slower |
| **LongFast (default)** | 11 | 250 | Standard public Meshtastic channel everywhere |
| LongModerate | 11 | 125 | Same SF, narrower band |
| LongSlow | 12 | 125 | Maximum range, very slow |

Set both `spreading_factor` and `bandwidth_khz` to match a preset. If you
omit them, the service uses the region's LongFast defaults.

---

## Custom Frequency Slots

Why you would deviate from the regional default frequency:

1. **You want a private channel that does not collide with the public mesh.**
   Public Meshtastic on US915 is on `906.875` (LongFast slot). Picking a
   different frequency in the band gives you a quiet experimental channel.
2. **Regulatory compliance.** Under FCC Part 15 in the US, narrowband
   non-hopping operation in 902-928 MHz is not authorized. Running BW 500
   with a moderate SF (e.g. SF9) is one common compliant configuration.
3. **You are testing or measuring.** Range tests, link budget validation,
   coverage characterization.

Example: 918.25 MHz, BW 500, SF 9, CR 4/5 (FCC Part 15 compliant
non-hopping configuration with good interference rejection):

```yaml
radio:
  region: "US"
  frequency_mhz: 918.25
  bandwidth_khz: 500.0
  spreading_factor: 9
  coding_rate: "4/5"
```

After changing the radio config, clearing local node and packet history
gives you a clean view of who is on the new slot:

```bash
sudo systemctl stop meshpoint
sudo rm /opt/meshpoint/data/concentrator.db
sudo systemctl start meshpoint
```

---

## US Slot Map (Meshtastic numbering)

Meshtastic apps refer to channels by **slot number**, but every Meshpoint
config field takes a frequency in MHz. Use this map to translate.

The Meshtastic firmware computes channel center frequency as:

```
freq = freqStart + (BW / 2000) + ((slot - 1) * (BW / 1000))
```

Note that user-facing slot numbers are **1-indexed** even though the
firmware decrements internally. This is the source of most off-by-one
errors when calculating slot frequencies by hand.

For US (`freqStart = 902.0 MHz`):

| BW | Channel spacing | Formula (slot N, 1-indexed) | # of slots |
|---|---|---|---|
| 125 kHz | 0.125 MHz | `902.0625 + (N - 1) * 0.125` | 208 |
| 250 kHz | 0.250 MHz | `902.125 + (N - 1) * 0.250` | 104 |
| 500 kHz | 0.500 MHz | `902.250 + (N - 1) * 0.500` | 52 |

### US BW250 (104 slots, default Meshtastic bandwidth)

| Slot | MHz | Slot | MHz | Slot | MHz | Slot | MHz |
|---:|---|---:|---|---:|---|---:|---|
| 1 | 902.125 | 27 | 908.625 | 53 | 915.125 | 79 | 921.625 |
| 2 | 902.375 | 28 | 908.875 | 54 | 915.375 | 80 | 921.875 |
| 3 | 902.625 | 29 | 909.125 | 55 | 915.625 | 81 | 922.125 |
| 4 | 902.875 | 30 | 909.375 | 56 | 915.875 | 82 | 922.375 |
| 5 | 903.125 | 31 | 909.625 | 57 | 916.125 | 83 | 922.625 |
| 6 | 903.375 | 32 | 909.875 | 58 | 916.375 | 84 | 922.875 |
| 7 | 903.625 | 33 | 910.125 | 59 | 916.625 | 85 | 923.125 |
| 8 | 903.875 | 34 | 910.375 | 60 | 916.875 | 86 | 923.375 |
| 9 | 904.125 | 35 | 910.625 | 61 | 917.125 | 87 | 923.625 |
| 10 | 904.375 | 36 | 910.875 | 62 | 917.375 | 88 | 923.875 |
| 11 | 904.625 | 37 | 911.125 | 63 | 917.625 | 89 | 924.125 |
| 12 | 904.875 | 38 | 911.375 | 64 | 917.875 | 90 | 924.375 |
| 13 | 905.125 | 39 | 911.625 | 65 | 918.125 | 91 | 924.625 |
| 14 | 905.375 | 40 | 911.875 | 66 | 918.375 | 92 | 924.875 |
| 15 | 905.625 | 41 | 912.125 | 67 | 918.625 | 93 | 925.125 |
| 16 | 905.875 | 42 | 912.375 | 68 | 918.875 | 94 | 925.375 |
| 17 | 906.125 | 43 | 912.625 | 69 | 919.125 | 95 | 925.625 |
| 18 | 906.375 | 44 | 912.875 | 70 | 919.375 | 96 | 925.875 |
| 19 | 906.625 | 45 | 913.125 | 71 | 919.625 | 97 | 926.125 |
| **20** | **906.875** (LongFast default) | 46 | 913.375 | 72 | 919.875 | 98 | 926.375 |
| 21 | 907.125 | 47 | 913.625 | 73 | 920.125 | 99 | 926.625 |
| 22 | 907.375 | 48 | 913.875 | 74 | 920.375 | 100 | 926.875 |
| 23 | 907.625 | 49 | 914.125 | 75 | 920.625 | 101 | 927.125 |
| 24 | 907.875 | 50 | 914.375 | 76 | 920.875 | 102 | 927.375 |
| 25 | 908.125 | 51 | 914.625 | 77 | 921.125 | 103 | 927.625 |
| 26 | 908.375 | 52 | 914.875 | 78 | 921.375 | 104 | 927.875 |

### US BW500 (52 slots, used for ShortTurbo and FCC Part 15 non-hopping)

| Slot | MHz | Slot | MHz | Slot | MHz | Slot | MHz |
|---:|---|---:|---|---:|---|---:|---|
| 1 | 902.250 | 14 | 908.750 | 27 | 915.250 | 40 | 921.750 |
| 2 | 902.750 | 15 | 909.250 | 28 | 915.750 | 41 | 922.250 |
| 3 | 903.250 | 16 | 909.750 | 29 | 916.250 | 42 | 922.750 |
| 4 | 903.750 | 17 | 910.250 | 30 | 916.750 | 43 | 923.250 |
| 5 | 904.250 | 18 | 910.750 | 31 | 917.250 | 44 | 923.750 |
| 6 | 904.750 | 19 | 911.250 | 32 | 917.750 | 45 | 924.250 |
| 7 | 905.250 | 20 | 911.750 | 33 | 918.250 | 46 | 924.750 |
| 8 | 905.750 | 21 | 912.250 | 34 | 918.750 | 47 | 925.250 |
| 9 | 906.250 | 22 | 912.750 | 35 | 919.250 | 48 | 925.750 |
| 10 | 906.750 | 23 | 913.250 | 36 | 919.750 | 49 | 926.250 |
| 11 | 907.250 | 24 | 913.750 | 37 | 920.250 | 50 | 926.750 |
| 12 | 907.750 | 25 | 914.250 | 38 | 920.750 | 51 | 927.250 |
| 13 | 908.250 | 26 | 914.750 | 39 | 921.250 | 52 | 927.750 |

---

## TX Power

```yaml
radio:
  tx_power_dbm: 22
transmit:
  enabled: false        # opt-in
  tx_power_dbm: 14
```

Two separate `tx_power_dbm` values exist:

- `radio.tx_power_dbm` (max 27): the SX1302 concentrator hardware ceiling.
  Affects what the chip is *capable* of producing.
- `transmit.tx_power_dbm` (default 14): the actual power used for native
  messaging from the dashboard. This is what you adjust day to day.

14 dBm (~25 mW) is conservative and compliant in most regions. Raise
carefully and check your regional ISM band limits before going above
20 dBm. Excess power into a poor antenna or improper grounding can damage
the radio.

---

## Duty Cycle

```yaml
transmit:
  # max_duty_cycle_percent omitted: auto-derives from radio.region
```

The percent of wall-clock time the radio is permitted to transmit. When
the key is absent (or set to `null`) the Meshpoint auto-derives a sane
default from `radio.region`:

| Region   | Default | Why                                           |
|----------|---------|-----------------------------------------------|
| `US`     | 10%     | FCC has no duty cycle rule, 10% is neighborly |
| `ANZ`    | 10%     | AS/NZS 4268 902-928 MHz unrestricted          |
| `KR`     | 10%     | KC has dwell-time, no duty cap                |
| `SG_923` | 10%     | IDA SG 920-925 MHz unrestricted               |
| `EU_868` | 1%      | ETSI hard cap on the LongFast sub-band        |
| `IN`     | 1%      | India 865-867 MHz mirrors ETSI                |

To override, set an explicit value in `local.yaml`:

```yaml
transmit:
  max_duty_cycle_percent: 25.0
```

`GET /api/config` returns the effective value plus
`max_duty_cycle_source` (`"auto"` or `"config"`) so the dashboard duty
gauge reflects the right cap.

The radio tab Stats card surfaces live duty cycle usage as a percentage
of this cap. To go back to auto-derive after pinning a value, delete the
`max_duty_cycle_percent` line from `local.yaml` and restart the service.

---

## Sync Word and Preamble

```yaml
radio:
  sync_word: 0x2B
  preamble_length: 16
```

`sync_word: 0x2B` is the Meshtastic standard. The `scripts/patch_hal.sh`
step in the v0.6.0 update specifically patches the libloragw HAL to use
this sync word for both RX and TX. **Do not change** unless you know
exactly why. Changing it will make your Meshpoint invisible to the
public mesh.

`preamble_length: 16` is the Meshtastic standard. Same advice.

---

## How the Radio Settings Page Maps to Config

Every field on the **Radio** settings page in the dashboard writes the
matching key in `local.yaml` and triggers a service restart:

| Dashboard field | Config key |
|---|---|
| Region | `radio.region` |
| Modem preset | `radio.spreading_factor` + `radio.bandwidth_khz` |
| Frequency | `radio.frequency_mhz` |
| TX power | `transmit.tx_power_dbm` |
| Duty cycle | `transmit.max_duty_cycle_percent` |
| TX enabled toggle | `transmit.enabled` |
| Long name | `transmit.long_name` |
| Short name | `transmit.short_name` |
| Hop limit | `transmit.hop_limit` |
| Channel 0 (primary) name | `meshtastic.primary_channel_name` |
| Custom channel + PSK | `meshtastic.channel_keys` |

Editing the YAML directly and restarting (`sudo systemctl restart meshpoint`)
has the exact same effect.

---

## Diagnosing What the Radio is Actually Doing

After any radio config change, the startup banner prints the actual
runtime configuration. Read the first 40 lines of the log:

```bash
meshpoint logs | head -40
```

Look for the radio summary block. If it shows the regional defaults when
you expected a custom slot, your YAML did not parse: validate with

```bash
sudo /opt/meshpoint/venv/bin/python -c "import yaml; print(yaml.safe_load(open('/opt/meshpoint/config/local.yaml')))"
```

Or use `meshpoint report` for a full operational view including current
radio config, traffic counts, signal averages, and system metrics.

---

## See Also

- [Configuration > Radio](CONFIGURATION.md#radio): full field reference
- [FAQ](FAQ.md#i-want-to-listen-on-a-custom-slot-bw500-sf9-custom-mhz-is-that-supported): quick answers
- [Common Errors > Configured custom frequency but hearing the public channel](COMMON-ERRORS.md#configured-custom-frequency-but-hearing-the-public-channel)
- [Onboarding > Changing MeshCore radio frequency](ONBOARDING.md#changing-meshcore-radio-frequency)
