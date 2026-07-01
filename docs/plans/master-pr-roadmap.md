# Meshpoint — Master PR Roadmap (16 PRs)

**Purpose:** Ordered pull-request queue across three feature-request batches. Submit **one at a time**; wait for merge or explicit feedback before opening the next.  
**Workflow:** [CONTRIBUTING.md](../../CONTRIBUTING.md) — branch from current `upstream/main`, one focused PR per branch, squash-merge on `KMX415/meshpoint:main`.  
**Risk tiers** (from CONTRIBUTING.md):

| Tier | Meaning |
|------|---------|
| 🟢 Green | Frontend or read-only backend — minimal review |
| 🟡 Yellow | New backend logic / config — standard review |
| 🔴 Red | Relay module or concentrator path — extra review |

**Sources:**

| Code | Suite |
|------|-------|
| FR1 | Feature Request 1 — Operator Diagnostics |
| FR2 | Feature Request 2 — Operator Intelligence |
| FR3 | Feature Request 3 — Field Operations |
| FR4 | Feature Request 4 — Remote Node Administration |

---

## Review status (your checklist)

Use this table to track what is **done**, **in flight**, or **not started**. Update the Status column as PRs merge.

| # | PR | Branch | Source | Risk | Status | Upstream PR |
|---|-----|--------|--------|------|--------|-------------|
| 01 | Packet Detail Modal | `feat/packet-detail-modal` | FR1 | 🟢 | ✅ Submitted | [#68](https://github.com/KMX415/meshpoint/pull/68) |
| 02 | Config QR Export | `feat/config-qr-export` | FR3 | 🟢 | ✅ Submitted | [#76](https://github.com/KMX415/meshpoint/pull/76) |
| 03 | 24-Hour Traffic Histograms | `feat/traffic-histograms` | FR1 | 🟢 | ✅ Submitted | [#69](https://github.com/KMX415/meshpoint/pull/69) |
| 04 | LAN Browser Push Notifications | `feat/lan-push-notifications` | FR3 | 🟢 | ✅ Submitted | [#77](https://github.com/KMX415/meshpoint/pull/77) |
| 05 | Per-Node Signal Health Sparklines | `feat/signal-health-tracking` | FR1 | 🟢 | ✅ Submitted | [#70](https://github.com/KMX415/meshpoint/pull/70) |
| 06 | Node Coverage Map Layer | `feat/node-coverage-map` | FR2 | 🟢 | ✅ Submitted | [#78](https://github.com/KMX415/meshpoint/pull/78) |
| 07 | Spectrum Analyzer Dashboard Tab | `feat/spectrum-analyzer-tab` | FR2 | 🟡 | ✅ Submitted | [#79](https://github.com/KMX415/meshpoint/pull/79) |
| 08 | Stray Frame Logger | `feat/stray-frame-logger` | FR3 | 🟡 | ✅ Submitted | [#80](https://github.com/KMX415/meshpoint/pull/80) |
| 09 | Prometheus Metrics Endpoint | `feat/prometheus-metrics` | FR2 | 🟡 | ✅ Submitted | [#81](https://github.com/KMX415/meshpoint/pull/81) |
| 10 | Event-Driven Webhook Engine | `feat/webhook-engine-config` | FR3 | 🟡 | ✅ Submitted | [#82](https://github.com/KMX415/meshpoint/pull/82) |
| 11 | Webhook Dashboard UI | `feat/webhook-ui` | FR3 | 🟢 | ✅ Submitted | [#83](https://github.com/KMX415/meshpoint/pull/83) |
| 12 | Storm Guard Auto-Quarantine | `feat/storm-guard-quarantine` | FR2 | 🔴 | ✅ Submitted | [#84](https://github.com/KMX415/meshpoint/pull/84) |
| 13 | Smart Relay Filter Controls | `feat/relay-filter-controls` | FR1 | 🔴 | ✅ Submitted | [#71](https://github.com/KMX415/meshpoint/pull/71) |
| 14 | USB Companion Firmware Flasher | `feat/companion-firmware-flasher` | FR3 | 🟡 | ✅ Submitted | [#85](https://github.com/KMX415/meshpoint/pull/85) |
| 15 | Remote Node Config Reader | `feat/remote-node-config-read` | FR4 | 🔴 | ✅ Submitted | [#86](https://github.com/KMX415/meshpoint/pull/86) |
| 16 | Remote Node Config Writer | `feat/remote-node-config-write` | FR4 | 🔴 | ✅ Submitted | [#87](https://github.com/KMX415/meshpoint/pull/87) |

**Legend:** ✅ Submitted · 🔄 In review · ⬜ Not started · ⏸ Blocked (waiting on dependency)

### Also submitted (parallel diagnostics track — not in the 13-PR queue)

These were built in the earlier [7-PR diagnostics suite](./operator-diagnostics-pr-list.md). They are **in scope** for Meshpoint but numbered separately in that plan:

| Diagnostics PR | Branch | Upstream PR | Notes |
|----------------|--------|-------------|-------|
| 5 — Visual Topology Graph | `feat/topology-graph-tab` | [#72](https://github.com/KMX415/meshpoint/pull/72) | FR2-adjacent; map/topology |
| 6 — LAN REST Automation API | `feat/lan-rest-api` | [#73](https://github.com/KMX415/meshpoint/pull/73) | FR3-adjacent; Home Assistant |
| 7 — Relay Duty-Cycle Throttle | `feat/relay-duty-cycle` | [#74](https://github.com/KMX415/meshpoint/pull/74) | 🔴 relay; depends on PR 03 + 13 logic |

**Recommended:** Let #68–#71 merge before opening #02–#12. Rebase any in-flight branch onto `main` after each merge.

### v0.7.8 operator polish (after Tier A / v0.7.7)

Green-tier operator UX that does not block the 16-PR queue. Full detail:
[`v0.7.8-operator-polish.md`](./v0.7.8-operator-polish.md).

| # | Branch | Risk | Status | Notes |
|---|--------|------|--------|-------|
| 17 | `feat/operator-polish` | 🟢 | ✅ [#90](https://github.com/KMX415/meshpoint/pull/90) | Status strips (Stats), MQTT runtime health, map GPS hint, HA cookbook |
| 18 | `feat/stats-traffic-heatmap` | 🟢 | 🔄 In progress | After **#69** merges; branches from `feat/traffic-histograms` |
| 19 | `feat/analytics-status-strips` | 🟢 | ✅ Partial | Footers on **#72, #79, #80**; Stats footer in **#90** |
| 20 | `docs/home-assistant-cookbook` | Docs | In #17 | Standalone doc also linked from README when #17 lands |

Submit **17** only after Tier A PRs begin landing. Never open 17 and 18 at once.

---

## Master table (submit in this order)

| # | Branch | Source | Risk | Relay? | Backend? | Frontend? | Depends on |
|---|--------|--------|------|--------|----------|-----------|------------|
| 01 | `feat/packet-detail-modal` | FR1 | 🟢 | No | No | Yes | — |
| 02 | `feat/config-qr-export` | FR3 | 🟢 | No | Minimal | Yes | — |
| 03 | `feat/traffic-histograms` | FR1 | 🟢 | No | One endpoint | Yes | — |
| 04 | `feat/lan-push-notifications` | FR3 | 🟢 | No | One WS field | Yes | — |
| 05 | `feat/signal-health-tracking` | FR1 | 🟢 | No | One endpoint | Yes | — |
| 06 | `feat/node-coverage-map` | FR2 | 🟢 | No | One endpoint | Yes | — |
| 07 | `feat/spectrum-analyzer-tab` | FR2 | 🟡 | No | One endpoint | Yes | — |
| 08 | `feat/stray-frame-logger` | FR3 | 🟡 | No | Table + insert | Yes | — |
| 09 | `feat/prometheus-metrics` | FR2 | 🟡 | No | One endpoint | No | — |
| 10 | `feat/webhook-engine-config` | FR3 | 🟡 | No | New module | No | — |
| 11 | `feat/webhook-ui` | FR3 | 🟢 | No | Two endpoints | Yes | **PR 10** |
| 12 | `feat/storm-guard-quarantine` | FR2 | 🔴 | Yes | Rate counter | Yes | [#84](https://github.com/KMX415/meshpoint/pull/84) |
| 13 | `feat/relay-filter-controls` | FR1 | 🔴 | Yes | Config R/W | Yes | — |
| 14 | `feat/companion-firmware-flasher` | FR3 | 🟡 | No | Subprocess + WS | Yes | — |
| 15 | `feat/remote-node-config-read` | FR4 | 🔴 | Yes | ADMIN TX read | Yes | **PR 14** |
| 16 | `feat/remote-node-config-write` | FR4 | 🔴 | Yes | ADMIN TX write | Yes | **PR 15** + 1 wk soak |

**Merge order:** 01 → 02 → … → 16 (ascending risk within each phase). **Never open two PRs at once.**

**Field hardware suite (14–16):** Submit **14**, wait for merge, then **15**, wait for merge + **≥1 week production soak**, then **16**.

---

## Shared prerequisites (every PR)

```bash
git fetch upstream
git checkout -B feat/<branch-name> upstream/main
```

**PR description must include:**

- What / why / how tested
- Hardware (RAK7248 or Pi + RAK2287/5146 HAT) and region (US915; EU868 where relevant)
- Risks (especially 🔴 relay PRs)
- `Closes #NNN` or `Related to #NNN`
- AI disclosure line (see [Submission notes](#submission-notes))

**Suggested GitHub issue (umbrella):**

> `[Feature] Master roadmap — diagnostics, intelligence, field operations, and remote admin (16 PRs)`

---

## PR 01 — Packet Detail Modal

| | |
|---|---|
| **Branch** | `feat/packet-detail-modal` |
| **Title** | `feat(dashboard): packet detail modal in live feed` |
| **Source** | FR1 |
| **Risk** | 🟢 Frontend only |
| **Status** | ✅ [#68](https://github.com/KMX415/meshpoint/pull/68) |

### Scope

Click any row in the live packet feed → layered modal (RF, mesh header, decoded payload, capture meta). Uses existing WebSocket `Packet.to_dict()` — **no new API**.

### Files (codebase-accurate)

| Layer | Files |
|-------|-------|
| Frontend | `frontend/js/simple_packet_feed.js` |
| Frontend | `frontend/js/packet_detail_modal.js` — **new** |
| Frontend | `frontend/css/packet_detail_modal.css` — **new** |
| Frontend | `frontend/index.html` — script/style tags |

*Roadmap text said `PacketFeed.js` — actual feed module is `simple_packet_feed.js`.*

### Done when

- [ ] Modal layers: RF, mesh, payload/decrypt, capture
- [ ] Decrypt-failure state explicit
- [ ] Close: ✕, Escape, backdrop
- [ ] Feed updates behind open modal
- [ ] Tested on target hardware

---

## PR 02 — Config QR Export

| | |
|---|---|
| **Branch** | `feat/config-qr-export` |
| **Title** | `feat(config): Quick Deploy QR export of public channel params` |
| **Source** | FR3 |
| **Risk** | 🟢 One read-only endpoint + frontend |
| **Status** | ⬜ Not started |

### Scope

"Quick Deploy" generates QR + downloadable JSON of **public** channel parameters (name, frequency, modem preset). **PSKs never included.** QR format matches Meshtastic channel URL scheme.

### Files

| Layer | Files |
|-------|-------|
| Backend | `src/api/routes/config_routes.py` (or new `export_routes.py`) — `GET /api/config/export` |
| Frontend | New QR panel (Configuration or Radio tab) + QR library (CDN or vendored) |
| Docs | `docs/CONFIGURATION.md` — export section |

### Endpoint (proposed)

```
GET /api/config/export
→ { channel_name, frequency_mhz, region, modem_preset, meshtastic_url, ... }
```

Read from existing `AppConfig` / `GET /api/config` enrichment — no secrets.

### Done when

- [ ] Response contains zero PSK / `channel_keys` material
- [ ] QR scans correctly in Meshtastic app
- [ ] JSON download works offline
- [ ] Auth: same as other config routes (`require_auth`)

---

## PR 03 — 24-Hour Traffic Histograms

| | |
|---|---|
| **Branch** | `feat/traffic-histograms` |
| **Title** | `feat(stats): 24-hour hourly traffic histogram with duty-cycle estimate` |
| **Source** | FR1 |
| **Risk** | 🟢 Frontend + one read-only SQL query |
| **Status** | ✅ [#69](https://github.com/KMX415/meshpoint/pull/69) |

### Scope

Hourly packet volume (24h), stacked Meshtastic/MeshCore, duty-cycle overlay (est.). EU868 1% limit line when `radio.region == EU_868`.

### Files

| Layer | Files |
|-------|-------|
| Backend | `src/storage/packet_repository.py` — `get_hourly_traffic()` |
| Backend | `src/api/routes/stats_routes.py` — `GET /api/stats/hourly` |
| Backend | `src/analytics/toa_estimate.py` — shared ToA helper |
| Frontend | `frontend/js/stats_tab.js`, `frontend/css/stats.css` |
| Tests | `tests/test_traffic_hourly.py` |

### Done when

- [ ] Hourly counts match manual SQL spot-check
- [ ] Duty line labeled **est.**
- [ ] EU868 limit line only when region matches
- [ ] No schema migration (uses `idx_packets_timestamp`)

---

## PR 04 — LAN Browser Push Notifications

| | |
|---|---|
| **Branch** | `feat/lan-push-notifications` |
| **Title** | `feat(dashboard): LAN browser push notifications for mesh alerts` |
| **Source** | FR3 |
| **Risk** | 🟢 Frontend + one additive WS field |
| **Status** | ✅ [#77](https://github.com/KMX415/meshpoint/pull/77) |

### Scope

Native browser notifications via Service Worker when operator-selected events occur (node offline/online, battery low, storm-guard trigger). Preferences in `localStorage`. Works while any dashboard tab is open.

### Files

| Layer | Files |
|-------|-------|
| Backend | WS broadcast schema — add optional `event_type: "alert"` (additive, non-breaking) |
| Frontend | Service worker — **new** (`frontend/sw.js` or similar) |
| Frontend | Notification settings UI (Configuration or global settings) |
| Frontend | `frontend/js/app.js` — WS handler for alerts |

### Depends on

- Nothing for basic alerts
- Storm-guard **content** needs PR 12 to emit quarantine alerts (can ship PR 04 with other triggers first)

### Done when

- [ ] Permission prompt + per-event toggles
- [ ] Existing WS packet stream unchanged when alerts disabled
- [ ] No notification when tab focused (optional UX)
- [ ] Tested in Chromium + Firefox

---

## PR 05 — Per-Node Signal Health Sparklines

| | |
|---|---|
| **Branch** | `feat/signal-health-tracking` |
| **Title** | `feat(nodes): RSSI sparklines and health badges on node cards` |
| **Source** | FR1 |
| **Risk** | 🟢 Frontend + read-only SQL per node |
| **Status** | ✅ [#70](https://github.com/KMX415/meshpoint/pull/70) |

### Scope

RSSI/SNR sparkline on node cards (24h, 15-min buckets), expandable in node drawer. Green/yellow/red badge from configurable thresholds in `local.yaml`. Lazy-loaded (`IntersectionObserver`).

### Files

| Layer | Files |
|-------|-------|
| Backend | `src/storage/packet_repository.py` — `get_signal_buckets()` |
| Backend | `src/api/routes/nodes.py` — extend `GET /api/nodes/{id}/metrics_history?bucket_minutes=15` |
| Config | `src/config.py` — `SignalHealthConfig` (optional) |
| Frontend | `frontend/js/signal_sparkline.js`, `frontend/js/node_cards.js` |
| Tests | `tests/test_signal_buckets.py` |

*Roadmap proposed `/signal_history` — **extend existing** `metrics_history` instead of a parallel endpoint.*

### Done when

- [ ] Sparkline loads only when card visible
- [ ] Badge hidden when packet count below `min_packets_per_hour`
- [ ] Thresholds documented in `CONFIGURATION.md`

---

## PR 06 — Node Coverage Map Layer

| | |
|---|---|
| **Branch** | `feat/node-coverage-map` |
| **Title** | `feat(map): RSSI coverage circles on dashboard map` |
| **Source** | FR2 |
| **Risk** | 🟢 Frontend + one read-only SQL JOIN |
| **Status** | ✅ [#78](https://github.com/KMX415/meshpoint/pull/78) |

### Scope

"Coverage View" toggle on existing Leaflet map. Nodes with GPS → color-coded circles (RSSI quality), size ∝ packet confidence. Nodes without GPS → "unplotted" count in sidebar. Click marker → existing node drawer.

### Files

| Layer | Files |
|-------|-------|
| Backend | `src/api/routes/nodes.py` — `GET /api/nodes/coverage` (JOIN nodes + packet aggregates) |
| Backend | `src/storage/node_repository.py` / `packet_repository.py` — aggregation helper |
| Frontend | `frontend/js/components/node_map.js` — coverage layer toggle |
| Frontend | `frontend/css/` — circle layer styles |

*Existing map: `NodeMap` in `node_map.js`; data today via `GET /api/nodes/map` → `NetworkMapper.get_map_data()`.*

### Done when

- [ ] Toggle does not break topology layer (PR diagnostics #5)
- [ ] Unplotted count accurate
- [ ] No new tile server
- [ ] Performance OK with 500+ nodes

---

## PR 07 — Spectrum Analyzer Dashboard Tab

| | |
|---|---|
| **Branch** | `feat/spectrum-analyzer-tab` |
| **Title** | `feat(rf): RF Environment tab exposing spectral scan + noise floor` |
| **Source** | FR2 |
| **Risk** | 🟡 New endpoint reading existing services |
| **Status** | ✅ [#79](https://github.com/KMX415/meshpoint/pull/79) |

### Scope

New **RF Environment** tab: noise-floor sparkline + calibration state; spectral histogram from latest scan. **Exposure only** — backend services already exist and are tested.

### Already in repo

| Component | Path |
|-----------|------|
| `NoiseFloorTracker` | `src/api/telemetry/noise_floor.py` |
| `SpectralScanService` | `src/api/telemetry/spectral_scan_service.py` |
| HAL scan | `src/hal/sx1302_spectral_scan.py` |
| Tests | `tests/test_noise_floor.py`, `tests/test_spectral_scan_*.py` |

### Files

| Layer | Files |
|-------|-------|
| Backend | `src/api/routes/rf_routes.py` — **new** — `GET /api/rf/status` |
| Backend | `src/api/server.py` — wire tracker + scan service into route init |
| Frontend | New RF tab JS + CSS; sidebar entry in `frontend/index.html` |

### Done when

- [ ] Tab shows "no hardware scan" gracefully when `spectral_scan_interval_seconds: 0`
- [ ] Values labeled live vs packet-derived fallback
- [ ] No new HAL code unless bugfix required

---

## PR 08 — Stray Frame Logger

| | |
|---|---|
| **Branch** | `feat/stray-frame-logger` |
| **Title** | `feat(capture): log undecodable RF frames to stray_frames table` |
| **Source** | FR3 |
| **Risk** | 🟡 New SQLite table + receive-path insert |
| **Status** | ✅ Submitted ([#80](https://github.com/KMX415/meshpoint/pull/80)) |

### Scope

When a frame fails **both** Meshtastic and MeshCore decode, persist RF metadata only (channel, frequency, SF, BW, RSSI, SNR, frame size) to `stray_frames`. Dashboard **Unknown RF** tab with filter + CSV export. Auto-prune by retention hours.

### Files

| Layer | Files |
|-------|-------|
| Storage | `src/storage/database.py` — migration for `stray_frames` |
| Storage | `src/storage/stray_frame_repository.py` — **new** |
| Pipeline | Insert after decode failure, before discard (coordinator / packet router) |
| API | `GET /api/stray_frames` (+ optional `?format=csv`) |
| Frontend | New tab or Stats subsection |
| Config | `stray_frames.max_retained` / `retention_hours` in `local.yaml` |

### Done when

- [ ] Insertion is **after** both decoders return None — no TX, no relay, no re-encode
- [ ] CSV export works
- [ ] Prune job does not block receive loop
- [ ] Unit test for repository + insert hook

---

## PR 09 — Prometheus Metrics Endpoint

| | |
|---|---|
| **Branch** | `feat/prometheus-metrics` |
| **Title** | `feat(metrics): Prometheus-compatible /metrics endpoint` |
| **Source** | FR2 |
| **Risk** | 🟡 New endpoint + optional config |
| **Status** | ✅ Submitted ([#81](https://github.com/KMX415/meshpoint/pull/81)) |

### Scope

`GET /metrics` in Prometheus text format: packet counts, duty-cycle est., noise floor, node counts, RSSI averages, CRC errors, relay stats, uptime. Read from in-memory state. **Disabled by default** (`metrics.enabled: false`). Optional `metrics.require_auth`.

### Files

| Layer | Files |
|-------|-------|
| Backend | `src/api/routes/metrics_routes.py` — **new** |
| Config | `src/config.py` — `MetricsConfig` |
| Docs | `docs/CONFIGURATION.md` |

**Implementation choice (decide before coding):**

- **A)** Zero-dep raw `# HELP` / `# TYPE` writer (preferred for Pi installs)
- **B)** Optional `prometheus_client` dependency

### Done when

- [ ] Default off — zero behaviour change on upgrade
- [ ] Document scrape config for LAN Prometheus
- [ ] No PSK / token values in labels

---

## PR 10 — Event-Driven Webhook Engine (Config Only)

| | |
|---|---|
| **Branch** | `feat/webhook-engine-config` |
| **Title** | `feat(webhooks): configurable outbound HTTP rules for mesh events` |
| **Source** | FR3 |
| **Risk** | 🟡 New async module + yaml schema |
| **Status** | ✅ Submitted ([#82](https://github.com/KMX415/meshpoint/pull/82)) |

### Scope

`local.yaml` webhook rules → async HTTP POST on events (battery low, node silence/return, keyword match, duty spike, storm quarantine). Per-rule cooldown in memory. Failures never block packet processing. Fires logged to audit log.

### Files

| Layer | Files |
|-------|-------|
| Backend | `src/webhook/engine.py` — **new** (or `src/integrations/webhook_engine.py`) |
| Config | `src/config.py` — `WebhookConfig` / rules list |
| Wiring | `src/coordinator.py` or packet callbacks — subscribe to decoded stream |
| Docs | `docs/CONFIGURATION.md` |

Uses `httpx` (already in stack). **No relay / TX / decoder changes.**

### Depends on

- Storm-guard **trigger** needs PR 12; all other triggers work independently

### Done when

- [ ] Failed POST does not slow pipeline
- [ ] Cooldown prevents alert storms
- [ ] Rules validated at startup
- [ ] Unit tests with mocked HTTP

---

## PR 11 — Webhook Dashboard UI

| | |
|---|---|
| **Branch** | `feat/webhook-ui` |
| **Title** | `feat(dashboard): webhook rules status and test panel` |
| **Source** | FR3 |
| **Risk** | 🟢 Frontend + thin API |
| **Status** | ✅ Submitted ([#83](https://github.com/KMX415/meshpoint/pull/83)) |
| **Depends on** | **PR 10 merged** ([#82](https://github.com/KMX415/meshpoint/pull/82)) |

### Scope

Settings panel: active rules from config, last-fired timestamps, **Test** button (dummy POST to verify URL from Pi).

### Files

| Layer | Files |
|-------|-------|
| Backend | `GET /api/webhooks/status`, `POST /api/webhooks/test/{rule_name}` |
| Frontend | Configuration card — **new** |

### Done when

- [ ] Test POST clearly marked dummy payload
- [ ] Last-fired updates without restart
- [ ] No rule secrets in API response

---

## PR 12 — Storm Guard Auto-Quarantine

| | |
|---|---|
| **Branch** | `feat/storm-guard-quarantine` |
| **Title** | `feat(relay): automatic storm/replay quarantine with auto-release` |
| **Source** | FR2 |
| **Risk** | 🔴 Relay module — **extra review** |
| **Status** | ✅ [#84](https://github.com/KMX415/meshpoint/pull/84) |

### Scope

Temporary **memory-only** quarantine for storm/replay behavior:

- Identical `packet_id` seen N times in rolling window, **or**
- Excessive packets/minute from one node

Separate from permanent blocklist (PR 13). Auto-release after duration. Amber badge + countdown on node cards. Operator can release early or promote to blocklist.

### Config (proposed — under `relay` section)

```yaml
relay:
  storm_guard:
    enabled: true
    window_seconds: 60
    identical_packet_threshold: 5
    rate_threshold_per_minute: 30
    quarantine_duration_seconds: 300
    notify_dashboard: true
```

### Files

| Layer | Files |
|-------|-------|
| Relay | `src/relay/storm_guard.py` — **new** |
| Relay | `src/relay/relay_manager.py` — check quarantine before approve |
| API | Optional `GET /api/relay/quarantine` for dashboard |
| Frontend | Node card badge; Relay / Stats section |
| WS | Optional `event_type: alert` for PR 04 |

### Risks (call out in PR)

- False positive quarantine on busy legitimate nodes
- Memory growth if quarantine dict not pruned
- Distinction from blocklist must be documented

### Done when

- [ ] Quarantine does not write SQLite
- [ ] Auto-release tested with clock injection
- [ ] Tested against fast TX test node
- [ ] `channel_throttled` / blocklist interaction documented

---

## PR 13 — Smart Relay Filter Controls

| | |
|---|---|
| **Branch** | `feat/relay-filter-controls` |
| **Title** | `feat(relay): dashboard blocklist, priority list, and dedup TTL` |
| **Source** | FR1 |
| **Risk** | 🔴 Relay + config — **extra review** |
| **Status** | ✅ [#71](https://github.com/KMX415/meshpoint/pull/71) |

### Scope

Dashboard UI for relay filters without editing `local.yaml`. Blocklist, priority list, dedup TTL. Hot-reload without restart.

### Files

| Layer | Files |
|-------|-------|
| Config | `src/config.py` — `relay.blocklist`, `priority_list`, `dedup_ttl_seconds` |
| Relay | `src/relay/relay_manager.py` — `reload_filters()` |
| API | `PUT /api/config/relay` in `system_config_routes.py` |
| Frontend | `frontend/js/configuration/relay_filters_card.js` |
| Tests | `tests/test_relay_filters.py` |

*Roadmap used flat keys `relay_blocklist` — actual schema nests under `relay:` in `local.yaml`.*

### Done when

- [ ] Blocklist is relay-only — feed unchanged
- [ ] Priority bypasses burst gate only (not per-minute cap)
- [ ] Node ID validated server-side (8 hex chars)
- [ ] Persistence across restart via `save_section_to_yaml`

---

## PR 14 — USB Companion Firmware Flasher

| | |
|---|---|
| **Branch** | `feat/companion-firmware-flasher` |
| **Title** | `feat(hardware): USB companion firmware flasher with live esptool output` |
| **Source** | FR3 |
| **Risk** | 🟡 Subprocess + WebSocket — **no radio TX** |
| **Status** | ✅ Submitted — [#85](https://github.com/KMX415/meshpoint/pull/85) |

### Scope

Upload a `.bin` from **Settings → System** and flash the USB MeshCore/Meshtastic companion via `esptool`. Live log stream on authenticated WebSocket. MeshCore USB releases serial before flash; auto-reconnect after ESP reboot.

### Files

| Layer | Files |
|-------|-------|
| Backend | `src/firmware/flasher.py`, `upload_store.py`, `log_broadcast.py` |
| Backend | `src/api/routes/firmware_routes.py` |
| Backend | `src/capture/meshcore_usb_source.py` — `release_serial_for_flash()` |
| Backend | `src/api/server.py` — router + MeshCore suspend hook |
| Frontend | `frontend/js/settings/companion_flash_card.js` |
| Deps | `requirements.txt` — `esptool>=4.7.0` |
| Tests | `tests/test_firmware_flasher.py` |
| Docs | `docs/CONFIGURATION.md` — companion flash section |

### Done when

- [x] Admin-only upload + flash; audit `firmware_flash`
- [x] WS uses `_gate_ws_or_close` pattern (4401 when unauthenticated)
- [x] Per-port lock; HTTP 409 on concurrent flash
- [x] Temp upload cleaned up on all paths
- [x] DangerousModal confirmation before flash POST
- [ ] Hardware flash on RAK7248 + Heltec companion

---

## PR 15 — Remote Node Config Reader (ADMIN, read-only)

| | |
|---|---|
| **Branch** | `feat/remote-node-config-read` |
| **Title** | `feat(admin): remote Meshtastic node config reader via ADMIN portnum` |
| **Source** | FR4 |
| **Risk** | 🔴 TX path — one ADMIN request per click |
| **Status** | ✅ Submitted — [#86](https://github.com/KMX415/meshpoint/pull/86) |

### Scope

**Request config** in node detail drawer. Sends encrypted `get_config_request` ADMIN packet; displays decoded response read-only. Requires `meshtastic.admin_key_b64` in `local.yaml`.

### Done when

- [x] No write path in this PR
- [x] 30 s timeout + retry UI; 30 s button debounce
- [x] PSK redacted in audit log
- [ ] Tested 1-hop and 3-hop on hardware

---

## PR 16 — Remote Node Config Writer (ADMIN write)

| | |
|---|---|
| **Branch** | `feat/remote-node-config-write` |
| **Title** | `feat(admin): remote Meshtastic node config write (limited fields)` |
| **Source** | FR4 |
| **Risk** | 🔴 **Highest in roadmap** — write TX + crypto |
| **Status** | ✅ Submitted — [#87](https://github.com/KMX415/meshpoint/pull/87) |

### Scope

Editable fields: names, telemetry interval, screen timeout, device role (typed `CONFIRM`). Post-write automatic config read to verify. No frequency/PSK/factory reset.

### Done when

- [x] Role change requires second confirmation
- [x] Follow-up read verifies applied state
- [ ] Hardware: role + telemetry interval change verified

---

## Submission strategy

| Phase | PRs | Goal |
|-------|-----|------|
| **A — Green baseline** | 01–06 (skip done: 01, 03, 05) | Establish clean contribution pattern |
| **B — Yellow backend** | 07–09 | After ≥2 green merges |
| **C — Webhooks** | 10 → 11 | Engine reviewed before UI |
| **D — Relay last** | 12 → 13 | Highest review; 13 already submitted — merge before PR 12 if both open |
| **E — Field hardware** | 14 → 15 → 16 | 14 no TX; 15–16 ADMIN TX; **1 week soak** between 15 and 16 |

**Never submit two PRs simultaneously.**

After each merge:

```bash
git fetch upstream
git checkout -B feat/<next-branch> upstream/main
```

---

## Scope alignment notes (roadmap vs repo)

| Roadmap item | Repo reality |
|--------------|--------------|
| `PacketFeed.js` | `frontend/js/simple_packet_feed.js` |
| `/api/nodes/{id}/signal_history` | Extend `GET /api/nodes/{id}/metrics_history` |
| `relay_blocklist` top-level keys | `relay.blocklist` under `relay:` in yaml |
| `relay_duplicate_window_sec: 30` | Implemented as `relay.dedup_ttl_seconds` (default 300) |
| `src/api.py` | Routes live under `src/api/routes/*.py` |
| Topology graph | Already PR diagnostics #5 ([#72](https://github.com/KMX415/meshpoint/pull/72)) — not in 13-PR table |
| Duty-cycle throttle | Already PR diagnostics #7 ([#74](https://github.com/KMX415/meshpoint/pull/74)) — after PR 03 + 13 |

---

## Operator test matrix (all PRs)

| Item | Value |
|------|-------|
| Primary hardware | RAK Hotspot V2 (RAK7248) or Pi 4 + RAK2287/5146 Pi HAT |
| Region | US915 primary; EU868 re-test for PR 03 duty line + PR 12/13 |
| OS | Raspberry Pi OS 64-bit Bookworm |
| Load profile | ~8k–12k packets/day backbone |
| MeshCore | Heltec V3 `companion_radio_usb` optional |

---

## Submission notes

### AI-assisted contributions

Per CONTRIBUTING.md, include in **each** PR description:

> Note: PR description and initial scaffolding assisted by Claude. All code reviewed and tested on target hardware before submission.

### What to say when starting each PR

| Step | Action |
|------|--------|
| Start next green PR | `git checkout -B feat/<branch> upstream/main` |
| After merge | Rebase or recreate branch from fresh `upstream/main` |
| Relay PR | Request extra review; document insertion point + failure modes |

### Suggested next PR (as of this doc)

With 01–13 submitted (02 also submitted as #76) and **14–16** queued:

1. **Waiting:** PR **16** [#87](https://github.com/KMX415/meshpoint/pull/87) in review — hardware role + telemetry verify
2. **Waiting:** PR **15** [#86](https://github.com/KMX415/meshpoint/pull/86) in review — hardware read 1-hop + 3-hop
3. **Waiting:** PR **14** [#85](https://github.com/KMX415/meshpoint/pull/85) in review (companion flash)
4. **Roadmap E complete** once 14–16 merge; soak #15 before #16 merge per strategy
4. Rebase open relay/webhook PRs (#80–#84) onto `main` as merges land

---

## Quick review checklist (per PR before submit)

- [ ] Branch from latest `upstream/main` (not stacked on another feature branch)
- [ ] Single focused change; no drive-by refactors
- [ ] Tests added or extended where backend logic changes
- [ ] `docs/CONFIGURATION.md` updated if new yaml keys
- [ ] No secrets in repo, logs, or API responses
- [ ] PR body: what / why / test plan / hardware / region / risks
- [ ] AI disclosure line present
- [ ] 🔴 Relay PRs: explicit "does not change TX to mesh" vs relay-only behaviour
