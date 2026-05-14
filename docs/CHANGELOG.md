# Changelog

### v0.7.2 (May 5, 2026)

Two-fix bundle on top of v0.7.1. One small UX feature for hop-chain debugging, one quiet-but-important correctness fix that was inflating node counts on the cloud catalog and producing intermittent garbled-but-readable text on the local mesh. Both ride together because they touch the same RX path. Pure-Python, no recompile needed.

- **Drop `STAT_CRC_BAD` packets at the HAL boundary instead of forwarding them to the decoder.** `SX1302Wrapper.receive()` was logging the diagnostic WARNING for CRC-failed packets but still appending them to the returned packet list, with `crc_ok=False` set on the `ConcentratorPacket`. No downstream code (`concentrator_source`, `packet_router`, decoders) ever read the `crc_ok` field, so RF-corrupted bytes flowed into `MeshtasticDecoder.decode()` where the source-ID was extracted directly from the corrupted header. Three observable downstream symptoms produced by this: (1) **phantom node IDs** registered in the local SQLite node table and propagated up to the cloud DynamoDB node catalog, where a single bit-flip in the source-ID field creates a new "node" sharing all-but-one bit with a real source ID; (2) **false ENCRYPTED packet attribution** when the channel-hash byte was corrupted and stopped matching the LongFast hash; (3) **garbled-but-readable text** when AES-CTR XORed corrupted ciphertext with the keystream, producing mostly-correct plaintext with a few mangled characters. Hardware-validated on RAK V2: 14 historical phantoms in the local DB matched the bit-flip fingerprint of legitimate neighbors (`7d8b98a9`, `a0dd8936`, etc.), and zero new phantoms have entered the database since the fix. Cloud-side `active_nodes_24h` count is expected to drop sharply over the 24-48h after fleet rollout. Closes [#34](https://github.com/KMX415/meshpoint/issues/34).
- **Relay-node visibility on the dashboard.** Surfaces the Meshtastic header `relay_node` byte (the lowest byte of the last relay node's ID) through the decoder → `Packet` model → SQLite schema (with idempotent `ALTER TABLE` migration for existing installs) → WebSocket payload → dashboard packet feed. Source cells in the packet feed now read `!source ↝ !relay` whenever the packet was relayed, with full short-ID resolution when the relay byte matches a known node in the local registry. Clicking a relayed packet draws a line on the map between the source marker and the relay marker so you can trace the hop chain visually. Direct (non-relayed) packets render as before. Real-world utility: tracing a hop chain back to a rooftop node and confirming its ERP from the RSSI/SNR pattern.
- **`hop_limit` on outbound TX now honors `TransmitConfig` instead of being hardcoded to 3.** Two paths (`send_text_message` and the NodeInfo broadcaster) were ignoring the configured hop limit and using a hardcoded `3` regardless of what was set in `local.yaml`. Behavior is unchanged for installs running the default (still 3); fixes the silent "I set `hop_limit` in my yaml and it didn't take" gap. The dashboard's per-packet HOPS column (`hop_used / hop_limit`) now reflects the actual configured ceiling.
- **Internal:** new `tests/test_sx1302_wrapper.py` covers the CRC_BAD drop contract (synthetic `STAT_CRC_BAD` input is dropped, `crc_bad_count` increments, the WARNING fires, the decoder is not reached). New `tests/test_relay_node_header.py` covers `relay_node` header byte parsing and `Packet.relay_node` population. `tests/test_database_migration.py` extended for the `packets.relay_node` ALTER TABLE path. 297 tests passing, ruff clean.

### v0.7.1 (April 30, 2026)

Polish bundle on top of the v0.7.0 source-publication release. Edge-only, no cloud changes. Touches radio tab UX, branding, and a handful of small upgrade-path papercuts. Pure-Python, no recompile needed.

- **Radio tab redesign.** Reworked the Radio tab with an SDR-console aesthetic: status lamps, readout cards, an analog-style duty-cycle gauge, a new NodeInfo Broadcast card, and a sticky restart banner that floats at the top while you scroll instead of getting buried at the bottom of the page. Channels table behavior is unchanged.
- **NodeInfo broadcast is now configurable from the dashboard.** New card on the Radio tab shows live telemetry (next broadcast countdown, last-sent timestamp, current interval, status lamp), exposes preset chips (`Off / 5m / 30m / 1h / 3h / 6h / 12h / 24h`) plus a free-form 5-1440 minute input, and a `Send Now` button that fires an immediate NodeInfo packet without waiting for the next scheduled tick. `interval_minutes: 0` pauses periodic broadcasts; non-broadcast TX (DMs, replies) is unaffected. New telemetry keys (`last_sent_at`, `next_due_at`, `running`) on `GET /api/config/nodeinfo`. New `POST /api/config/nodeinfo/send` endpoint.
- **Interval changes hot-reload without a service restart.** Saving a new NodeInfo interval immediately wakes the broadcast loop and re-anchors the next-due time, including during the initial 60-second startup delay window. Pausing (`interval=0`) cleanly idles the loop; resuming fires the next broadcast right away if one was already overdue. Only `startup_delay_seconds` changes still require a restart, and the UI says so.
- **Pending-changes cue on Save buttons.** When the displayed NodeInfo interval differs from the saved value, an amber notification dot pulses at the top-right of the Save button so unsaved work is hard to miss. Clears automatically on save or page refresh.
- **Save NodeInfo card auto-refreshes after a broadcast fires.** Previously the countdown got stuck on "broadcasting..." until you reloaded the page.
- **Send Advert button on the MeshCore Companion card now actually works.** Previously it POSTed to the text-message endpoint with empty body, got rejected by the empty-text validation, and surfaced "Advert failed" with nothing in the logs. Added a dedicated `POST /api/messages/advert` endpoint that calls `MeshCoreTxClient.send_advert()` directly. Reported by iceice400.
- **Branding consistency pass.** All user-facing prose and log lines now read "Meshpoint" and "Meshradar" (one word, capital M) instead of "Mesh Point" and "Mesh Radar". Most importantly, the default Meshtastic NodeInfo `long_name` broadcast over RF now reads `Meshpoint`, so the device shows up correctly on `meshmap.net`, the Meshtastic phone app, and neighbor MQTT envelopes. Other surfaces touched: dashboard header, browser tab title, FastAPI auto-docs, CLI prose (`meshpoint setup`, `meshpoint status`, `wizard_meshcore`), installer prose, systemd unit descriptions, and module docstrings. Code identifiers (CLI command name, Python module names, YAML keys) are unchanged: branding rule applies to prose only.
- **Duty cycle default now auto-derives from your region.** Previously hardcoded to `1.0` (the EU 1% etiquette ceiling) regardless of where you were. New `resolve_max_duty_percent()` reads `radio.region` and applies a conservative regional default (US: 10%, EU 868: 1%, ANZ: 10%, IN: 1%, KR: 1%, SG 923: 10%) unless `relay.max_duty_percent` is explicitly set in `local.yaml`. Source surfaced in the Radio tab duty gauge as `region_default` vs `user_override`. See `docs/RADIO-CONFIG-EXPLAINED.md` for how to override.
- **Mobile responsive polish.** All four dashboard tabs (Dashboard, Stats, Messages, Radio) render cleanly on phone-width viewports. Validated with the official Playwright MCP at iPhone 14 Pro and Galaxy S24 viewports.
- **Header `Meshradar` brand link.** The "Meshradar" portion of the dashboard header is now a link to `meshradar.io` (opens in new tab). The "Meshpoint" portion stays plain text. Requested by Parker WEST.
- **Setup wizard preserves your existing coordinates.** Example coordinates in the location prompt now show neutral NYC values (`40.7128, -74.0060`) instead of a developer-specific location. Existing `device.latitude` / `device.longitude` in `local.yaml` are still preserved as the prompt default, so re-running `meshpoint setup` does not overwrite them.
- **`install.sh` upgrade-aware banner.** When run on a Meshpoint that already has an existing install (detected via `config/local.yaml` presence or `meshpoint.service` enabled), the closing banner now reads "Meshpoint upgrade to vX.Y.Z complete: restart the service" instead of the spurious "Reboot to apply SPI/UART changes" message that was misleading users on every v0.7.0+ upgrade. Fresh installs still see the full first-run flow.
- **MQTT topic clarification in `default.yaml`.** Added inline comments explaining that `mqtt.topic_root` and `mqtt.region` are concatenated to form the full Meshtastic spec topic (`<topic_root>/<region>/2/e/<channel>/<gateway>`), and that `mqtt.region` is independent of `radio.region`. Avoids the double-region footgun (`msh/US/FL/US/...`) where users assume `topic_root` is the complete prefix.
- **FastAPI app version follows `__version__`.** The auto-generated `/docs` Swagger header was hardcoded to `0.1.0` since v0.1.x. Now reads from `src.version.__version__` so it matches the running release.
- **Internal:** new `tests/test_messages_advert_route.py` (5 tests, FastAPI TestClient pattern), `tests/test_nodeinfo_broadcaster.py::TestNodeInfoBroadcasterHotReload` (10 tests covering hot-reload, pause, resume, startup-delay interruption), `tests/test_duty_cycle_resolver.py` (region resolution + override semantics). 254 tests passing, ruff clean.

### v0.7.0 (April 28, 2026)

Distribution architecture change: the eleven core SX1302/MeshCore modules are now shipped as Python source files in `src/{hal,capture,decode,transmit}/` instead of pre-compiled `.cpython-*.so` binaries. Behavior is identical to v0.6.8; the change is purely about distribution format. Closes issue #32.

- **Source published.** All eleven modules (HAL wrapper, channel-plan builder, GPS reader, concentrator capture source, SX1262 SPI source, AES-CTR crypto service, Meshtastic and Meshcore decoders, portnum handlers, packet router, Meshtastic packet builder) ship as plain `.py` files under the existing AGPL-3.0 license. Auditability and portability to non-aarch64 hardware become trivial.
- **Upgrade path uses `install.sh`.** `scripts/install.sh` now removes any `.cpython-*.so` left behind by previous installs before the venv is set up. After `git pull`, run `sudo /opt/meshpoint/scripts/install.sh` followed by `sudo systemctl restart meshpoint`. A `git pull` alone is not sufficient on existing v0.6.x devices: Python's import machinery would prefer the stale binary over the new source.
- **Boot-time stale-`.so` detection.** A startup WARN fires (and lists the offending files) if compiled binaries somehow re-appear in `src/`. Surfaces in `meshpoint logs` so you can fix the install before behavior freezes at v0.6.x.
- **RX diagnostic logging.** Every CRC_BAD packet on the SX1302 concentrator now logs a WARNING with the IF chain, SF, BW, RSSI, SNR, size, and a running CRC_BAD counter. Useful for diagnosing rapid-fire packet loss caused by overlapping LoRa transmissions on the same demodulator. Per-packet RX traces are also available via the new `MESHPOINT_DEBUG_RX=1` environment variable (off by default).
- **Internal:** retired the Cython build pipeline that produced the per-release `.cpython-*.so` artifacts since it's no longer needed.

### v0.6.8 (April 26, 2026)

Pure-Python follow-up to v0.6.7. No core module recompile required: just `git pull` + `systemctl restart`. Fixes two user-visible regressions surfaced after v0.6.7 shipped, plus the long-standing `PRIVATE_HW` labeling on community maps.

- **Auto-derived Node ID is now persisted to `local.yaml` on first boot.** v0.6.7 added stable Meshtastic identity but only displayed the derived value on the dashboard if you happened to also save the Radio settings page; until then the API kept returning `node_id_hex: ""` and the field rendered blank. Reported by Parker WEST. The Meshpoint now writes the derived value to `transmit.node_id` automatically the first time it falls back to the `device_id` derivation, then treats it as a normal pinned config value on every subsequent restart. Hint text on the Radio tab tracks the source ("Pinned in local.yaml. Edit to override." vs "Random fallback (no device ID configured).") so you can tell at a glance where the value came from. End-to-end validated on RAK V2 with a fresh derive → persist → reload cycle.
- **Hardware model now reports as `PORTDUINO` (37) instead of `PRIVATE_HW` (255).** Reported by holmebrian. Other Meshpoints, MQTT gateways, and `meshmap.net` were displaying every Meshpoint as the generic "private hardware" label even though Meshtastic has had a `PORTDUINO` enum value for Linux-based nodes since 2.4. New `HW_MODEL_PORTDUINO` constant alongside the existing `HW_MODEL_PRIVATE_HW`, threaded through `NodeInfoBroadcaster` as the default. Verified on a witness Meshtastic phone after the broadcast cycle (60 s after restart, then every 30 min). Existing nodes will pick this up automatically on their next NodeInfo decode.
- **Local Stats tab "Network" section now actually renders.** The Hardware Models donut on the local dashboard was hidden for everyone, even though the underlying SQLite query was returning data (143 of 458 nodes had a populated `hardware_model` column on the test RAK). Two bugs: (1) the section was section-level hidden until **roles** had data, but the deferred edge decoder bug filters role 0 (= `CLIENT`, the most common role) out at decode time, so roles is effectively always empty on v0.6.x; (2) the `HW_NAMES` lookup table on the frontend had drifted from the upstream Meshtastic `HardwareModel` enum, so any model that DID render was getting the wrong label. Fixed both: each chart now hides itself independently, the section appears as long as either has data, and `HW_NAMES` is regenerated from `mesh.proto` (covers 0..129 plus 255). The Device Roles chart will start populating once the v0.7.0 core module bundle ships the deferred decoder fix.
- **Internal:** new `node_id_source` property on `TxService` ("config" / "derived" / "random") for API + dashboard introspection. New `persist_derived_node_id` constructor flag for test isolation. Eight new tests covering source-tracking and the auto-persist path (success, no-op when pinned, no-op when random, swallowed PermissionError). Two new tests on `NodeInfoBroadcaster` for the PORTDUINO default + override.

### v0.6.7 (April 25, 2026)

Stable Meshtastic identity, NodeInfo broadcasts, and a clutch of small reliability fixes. **Core module recompile required.** Fixes Meshtastic DMs sent from a Meshpoint never arriving at recipients, even though the dashboard showed "Sent". Reported by Max_Plastix.

- **Stable `source_node_id` per Meshpoint.** Previously the Meshtastic node ID was randomly chosen on every service restart unless the user manually set `transmit.node_id` in `local.yaml` or via the dashboard radio tab. Recipients ended up seeing a brand new "ghost" Meshpoint each restart and never built a stable contact, so direct messages had nowhere to thread to. Resolution priority is now (1) `transmit.node_id` in config, (2) deterministic SHA-256 derivation from the provisioned `device.device_id` UUID (stable across reboots), (3) cryptographically random fallback with a startup WARN if neither is set. Reserved IDs (`0x00000000`, `0xFFFFFFFF`) are explicitly skipped. Existing manually-set node IDs are preserved.
- **Periodic NodeInfo broadcasts.** New `NodeInfoBroadcaster` advertises the Meshpoint's identity (long name, short name, node ID, hardware model `PRIVATE_HW`) on the mesh 60 seconds after startup and every 30 minutes after that. This is what makes recipient nodes (T-Beam, Heltec, etc.) form a contact for your Meshpoint so they can route DMs back to it. Same `source_node_id` is used for both NodeInfo and outbound DMs/text so recipients see one consistent identity.
- **Setup wizard surfaces the resolved identity.** The `meshpoint setup` Device step now prints the device ID, derived node ID, long name, and short name with their origin (`existing config` vs `auto-generated`) so you can see exactly what will be advertised on the mesh before saving.
- **Setup wizard preflight check.** `meshpoint setup` now verifies write permission to `config/local.yaml` and the existence of the `config/` directory **before** asking any of the eight questions, so it bails immediately with an actionable message instead of failing 60 seconds in after you've filled in the whole form. Hit by holmebrian during initial setup.
- **Wizard config preservation (carried over from disk).** Untouched sections of `local.yaml` (e.g. `meshcore_usb`, `mqtt`) are now preserved when re-running `meshpoint setup`, instead of getting wiped out by the wizard overlay. New `_deep_merge` helper handles nested merges. 13 unit tests cover the merge semantics.
- **Relay marked experimental, log noise tamed.** Relay TX has never worked end-to-end (see ROADMAP.md). When `relay.enabled: true` you now get a one-line WARN banner at startup making this explicit. The per-packet `Relay TX: no payload available` warning now fires only once per process and drops to DEBUG for every subsequent skip, so logs stay readable while the v0.7.0 relay completion is in flight.
- **Cross-protocol sender-name leak in DMs fixed.** Meshtastic inbound DMs were showing arbitrary MeshCore contact names ("Guzii_RedV4" leaking into a Meshtastic conversation, etc.) because the unscoped fallback in `_save_and_notify` grabbed the first available `mc:%` node row regardless of the inbound packet's protocol, then **persisted that wrong name back to the Meshtastic node row** so it stuck across reconnects. Each fallback is now scoped to its own protocol, and a parallel Meshtastic source-id lookup now runs for inbound MT direct messages (mirroring the existing broadcast path). Found mid-validation while testing the v0.6.7 NodeInfo fix.
- **Auto-cleanup of pre-v0.6.7 contamination.** New idempotent startup migration in `DatabaseManager` repairs Meshtastic node rows whose `long_name` was overwritten by a MeshCore contact name in earlier versions. Affected rows have their `long_name` reset to NULL on first restart of v0.6.7; the next NodeInfo broadcast from the real node repopulates the correct name automatically. Migration is a no-op on clean databases. (Previously-stored corrupted message rows in the `messages` table are not auto-repaired since they're an immutable per-message snapshot; delete the affected conversation if the historical naming bothers you.)
- **`docs/COMMON-ERRORS.md`** gains entries for "Meshtastic DM shows Sent but recipient never gets it" (now fixed in v0.6.7) and "Two Meshpoints with the same node ID breaking the mesh" (only happens if you `dd` clone an SD card without re-running `scripts/provision.py`).
- **`docs/RADIO-CONFIG-EXPLAINED.md`** documents the three identity sources (dashboard / wizard / yaml), their resolution priority, and the fact that identity changes require a service restart.
- **Internal:** new tests for `_resolve_node_id` (8 cases), `NodeInfoBroadcaster` (8 cases), `build_nodeinfo` round-trip through the decoder (8 cases, private repo), wizard preflight (4 cases), and the relay no-payload dedup (4 cases). 32 new tests total, all green.

### v0.6.6 (April 25, 2026)

MeshCore reliability patch. Small follow-up to v0.6.5 cleaning up rough edges around the MeshCore USB companion. No edge concentrator changes, no cloud changes.

- **Companion connects cleanly on `systemctl restart meshpoint`.** ESP32-S3 boards (Heltec V3/V4 etc.) need 6-10 seconds to be USB-ready after a reboot, but the underlying meshcore library was giving up after 5. Bumped the handshake window so cold connects work the first time instead of needing a manual USB unplug.
- **Background reconnect with DTR soft-reset.** When the initial handshake does miss anyway, the source now schedules a background reconnect with exponential backoff and pulses DTR low to soft-reset the chip on the second attempt onwards. Recovers in 30-50 seconds without user intervention. On boards where DTR is wired to RESET (the common case for ESP32 dev boards) this is a real hardware reset; on others it's a harmless no-op.
- **Health check tuning.** The MeshCore health check (in place since March) was sometimes treating slow but healthy responses as a dead connection and triggering a full reconnect cycle. We caught it on the RAK during this round of testing: every 2-3 minutes the source would tear down and rebuild, costing 15-20 seconds of MeshCore RX downtime each time. Whether this was happening on other Meshpoints in production is unknown; it was never surfaced as a user-visible symptom. The health check now passes a proper command timeout, skips the active probe when inbound events have arrived recently (proof of life), and tolerates a single transient miss before declaring the connection dead.
- **Dashboard radio tab now shows real values.** The MeshCore Companion card was stuck on `Name: Unknown / Frequency: ? MHz / SF: SF? / TX Power: ? dBm` for everyone. Dashboard was reading from the wrong source. It now reads from the same place the `meshpoint meshcore-radio` CLI does, which has always shown correct values.
- **Smarter `meshpoint meshcore-radio` CLI.** Now prompts for a full Pi reboot after applying new radio settings instead of doing a service restart that races the still-recovering USB CDC stack. Reboot is the reliable path; restarting the service mid-USB-enumeration leaves MeshCore in a half-connected state where messages don't flow.
- **Heltec V4 ACM-shift fix.** The companion would temporarily move from `/dev/ttyACM0` to `/dev/ttyACM1` during the post-config reboot, get pinned into your `local.yaml`, then become unreachable after the next Pi reboot when the kernel re-assigned it back to `/dev/ttyACM0`. The CLI now switches your config to `auto_detect: true` whenever it sees the port shift, so the companion is found wherever it lands across reboots.
- **`docs/COMMON-ERRORS.md`** gains entries for the MeshCore handshake-failed log message and spurious health-check reconnects.
- **Demoted `No MeshCore USB device found` from WARNING to INFO** with friendlier wording (it's an expected state if the source is enabled but no companion is currently plugged in, not an error).
- **Internal:** fixed deprecated `asyncio.get_event_loop()` pattern in `tests/test_message_repository.py` so the suite remains compatible with newer test files using `IsolatedAsyncioTestCase`.

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
