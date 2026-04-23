# Changelog

### v0.6.5 (April 22, 2026)

- **Network watchdog reliability fix:** the watchdog no longer triggers an infinite reboot loop on networks where the gateway blocks ICMP. Gateway pings now fall back to `8.8.8.8` before a check is counted as a failure, and **auto-reboot is disabled by default** (`REBOOT_THRESHOLD = 0`). Stage 1 recovery (interface restart at 3 consecutive failures) is unchanged. To re-enable automatic reboots, edit `scripts/network_watchdog.py` and set `REBOOT_THRESHOLD` back to `6`. Startup banner now logs the active thresholds so you can confirm the policy at a glance. Thanks to first-time contributor [@dotchance](https://github.com/dotchance) for catching this and shipping the fix. ([#27](https://github.com/KMX415/meshpoint/pull/27))
- **Support documentation expansion:** new `docs/FAQ.md`, `docs/HARDWARE-MATRIX.md`, `docs/COMMON-ERRORS.md`, `docs/RADIO-CONFIG-EXPLAINED.md`, and `docs/MQTT-AND-MESHRADAR.md`. README "Support and documentation" section reorganized into Setup / When-something-goes-wrong / Project groups.
- **SX1302 minimum bandwidth documented:** `docs/HARDWARE-MATRIX.md` and `docs/RADIO-CONFIG-EXPLAINED.md` now explain that the SX1302 concentrator cannot tune below 125 kHz, which is why MeshCore (62.5 kHz) requires a USB companion radio for RX.

### v0.6.4 (April 16, 2026)

- **Meshtastic broadcast sender names:** received messages on public channels (LongFast, etc.) now show the sending node's long name, short name, or hex ID. Previously the UI showed the conversation key (`broadcast:meshtastic:0`) in place of the sender because the backend never resolved the source node for Meshtastic broadcast text packets. The v0.6.2 sender-name fix only covered MeshCore; this finishes the job for Meshtastic. ([#19](https://github.com/KMX415/meshpoint/issues/19))
- **Defensive frontend filter:** chat UI no longer renders strings starting with `broadcast:` as a sender label if they ever slip through.

### v0.6.3 (April 16, 2026)

- **TX channel hash fix:** messages sent from the dashboard were going out with hash 0x02 (invisible to the mesh) instead of the correct 0x08. The primary channel name defaulted to blank, producing the wrong hash. Now defaults to "LongFast" matching Meshtastic firmware. ([#21](https://github.com/KMX415/meshpoint/issues/21))
- **Primary channel editable:** channel 0 can now be renamed and saved from the Radio settings page. Previously edits reverted on refresh. ([#13](https://github.com/KMX415/meshpoint/issues/13))
- **Channel display cleanup:** Radio settings shows the actual channel name (e.g. "LongFast") instead of "Primary (LongFast)".

### v0.6.2 (April 16, 2026)

- **MQTT channel name fix:** MQTT topics now use the actual channel name (LongFast, MediumFast, ShortFast, etc.) instead of `chXX` hashes. New `ChannelResolver` maps all 8 standard Meshtastic presets and supports user-configured channel keys. ([#20](https://github.com/KMX415/meshpoint/issues/20))
- **Chat sender names:** received messages now show the sender's node name or hex ID. Previously there was no way to tell who sent what. ([#19](https://github.com/KMX415/meshpoint/issues/19))
- **Chat day dividers:** messages from different days are separated by date labels (Today, Yesterday, or the date) in the chat window.
- **Espressif USB udev rule:** installer adds a udev rule so Heltec V3/V4 and T-Beam ESP32-S3 USB serial devices are accessible to the meshpoint service user without manual group changes. ([#12](https://github.com/KMX415/meshpoint/issues/12))

### v0.6.1 (April 11, 2026)

- **Local stats dashboard:** new Stats tab on the local dashboard with 12 live Chart.js charts: protocol split, packet types, RSSI distribution, signal quality, direct vs relayed, active nodes, device roles, hardware models, relay decisions, rejection reasons, and traffic timeline. All generated locally, no cloud needed.
- **Enriched heartbeat:** edge accumulates per-packet stats in memory and sends a batched summary to Meshradar in each heartbeat instead of the cloud processing every individual packet. Same data, significantly fewer backend operations. Savings scale with fleet size.
- **Local topology layer:** map tab gains a "Topology Links" toggle showing lines between nodes with RSSI/SNR tooltips.
- **Farthest direct tracking:** tracks the farthest direct (0-hop) node heard, with distance and signal strength, visible on the stats page.
- **Relay rejection tracking:** relay engine now records why packets are rejected (duplicate, rate limited, type filtered, signal bounds), visible in local stats.

### v0.6.0 (April 8, 2026)

- **Native mesh messaging:** send and receive Meshtastic messages from the browser. Broadcast to LongFast, talk on custom channels, DM individual nodes. MeshCore messaging via USB companion. SX1302 transmits with correct sync word and encryption.
- **Chat UI:** conversations organized by channel and contact. Signal info on every received bubble. Duplicate badge for relayed messages. History persisted locally.
- **Radio config from dashboard:** region, modem preset, frequency override, TX power, duty cycle, custom channels with PSKs, and TX toggle. All configurable from the Radio tab without SSH.
- **Node discovery:** live node cards with name, ID, protocol, hardware model, signal, battery, last seen. Detail drawer with signal history. DM from node card.
- **Dashboard overhaul:** messaging tab, node cards grid, radio settings page, frequency and SF columns in packet feed.
- **CLI operational report:** `meshpoint report` command with full-screen terminal dashboard: RX stats, traffic breakdown, signal averages, system metrics, health status.
- **Setup wizard improvements:** unique random Meshtastic node ID per device (no collisions), MeshCore companion as its own wizard step.

### v0.5.5 (April 2, 2026)

- **MQTT hotfix:** shipped missing MQTT runtime files (publisher, formatter, pipeline wiring) that were absent from v0.5.4. MQTT config and docs were present but the code was not, so `mqtt.enabled: true` had no effect. Update and restart to activate MQTT publishing.

### v0.5.4 (March 30, 2026)

- **MQTT gateway:** dual-protocol MQTT publishing for Meshtastic (protobuf ServiceEnvelope) and MeshCore (JSON). Publishes to community maps (meshmap.net, NHmesh.live) and Home Assistant. Two-gate privacy model: MQTT is off by default, and only public channel traffic is published unless you explicitly allowlist a private channel. Each Meshpoint gets a unique node-format gateway ID that integrates natively with the Meshtastic ecosystem, appearing on meshmap.net, Liam Cottle's map, and other community tools. Optional JSON mirror for HA/Node-RED, auto-discovery sensor configs, and configurable location precision.
- **Packet type filter (cloud):** filter the Meshradar cloud packet feed by type (traceroute, position, text, etc.) and protocol (Meshtastic/MeshCore). Dropdown filters in the packets tab header.
- **Setup wizard MQTT step:** `meshpoint setup` now includes an MQTT opt-in prompt with broker selection and HA integration toggle.

### v0.5.3 (March 31, 2026)

- **Multi-key decryption:** packets on private Meshtastic channels now decrypt when channel keys are configured in `local.yaml`. Previously only the default key was tried. ([#5](https://github.com/KMX415/meshpoint/issues/5))
- **Heartbeat optimization:** reduced upstream heartbeat interval for lower cloud costs.

### v0.5.2 (March 31, 2026)

- **Core module binary fix:** v0.5.1 shipped updated source but stale compiled `.so` files. This release includes the correctly compiled binaries.

### v0.5.1 (March 30, 2026)

- **Non-LongFast preset fix:** `ConcentratorChannelPlan.from_radio_config()` no longer ignores spreading factor and bandwidth when using the region's default frequency. EU_868 MediumFast (SF9/BW250), ShortFast, and other presets now work correctly. Previously, any preset at the default frequency was silently overridden to LongFast (SF11/BW250). ([#4](https://github.com/KMX415/meshpoint/issues/4))

### v0.5.0 (March 29, 2026)

- **Multi-region frequency support:** 6 Meshtastic regions (US, EU_868, ANZ, IN, KR, SG_923) with auto-tuning concentrator and setup wizard region selector.
- **Preset tuning:** service channel SF and BW are configurable via `local.yaml`. Supports MediumFast, ShortFast, ShortTurbo: not just LongFast.
- **Frequency override:** set `frequency_mhz` in `local.yaml` to tune to a non-default slot within your region.
- **Full portnum decoding:** position speed/heading/altitude, power metrics, routing errors, NEIGHBORINFO, TRACEROUTE payloads.
- **`meshpoint meshcore-radio` CLI:** switch MeshCore companion frequency without re-running the full wizard. Presets (US/EU/ANZ) or custom entry.
- **Startup banner accuracy:** boot log shows the actual radio config, not just the region default.
- **Config stability:** empty YAML sections no longer crash the service on startup.

### Earlier (March 2026)

#### Early March
- **Real-time packet streaming:** cloud dashboard receives packets instantly via WebSocket. Live animated lines trace packets from source nodes to your Meshpoint on the map.
- **Cloud map overhaul:** marker clustering, signal heatmap layer, topology lines from neighborinfo data, and a live Recent Packets ticker panel.
- **SenseCap M1 support:** auto-detects SenseCap M1 carrier board via I2C probe during setup. Flash an SD card and go.
- **14 Meshtastic portnums decoded:** TEXT, POSITION, NODEINFO, TELEMETRY, ROUTING, ADMIN, WAYPOINT, DETECTION_SENSOR, PAXCOUNTER, STORE_FORWARD, RANGE_TEST, TRACEROUTE, NEIGHBORINFO, MAP_REPORT, plus encrypted packet tracking.
- **Device role extraction:** node table shows CLIENT, ROUTER, REPEATER, TRACKER, SENSOR, and other roles from NodeInfo packets.
- **Smart relay engine:** deduplication, token-bucket rate limiting, hop/type/signal filtering, independent SX1262 TX path.

#### Mid March
- **Live dashboard UX:** color-coded packet feed, decoded payload contents, 24h active node counts, version-based update indicator, and enlarged map view.
- **Cloud dashboard tabs:** tabbed layout with fleet view, interactive map controls, device-scoped filters, unified packet cards with signal strength bars, and public activity stream for visitors.
- **MeshCore USB capture:** new capture source for USB-connected MeshCore companion nodes. Auto-detects the device, configures radio frequency via the setup wizard (US/EU/ANZ presets or custom), with auto-reconnect and health monitoring. Startup banner shows all active sources.
- **Custom frequency tuning:** configurable SX1302 channel plan via `local.yaml`. Validated on live hardware with LongFast (SF11/BW250). Dual-protocol HAL patch for simultaneous Meshtastic and MeshCore sync words.
