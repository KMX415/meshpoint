# Configuration — Identity, Radio, Channels, Transmit, MQTT, GPS

Read/write home for everything that lands in `local.yaml`. Six subsections, each with their own walkthrough.

## 1. Configuration > Identity

**Status:** [ ] Not started  [ ] In progress  [ ] Pass  [ ] Blocked
**Hardware:** `.141` and `.15`

### Functional walkthrough

1. [ ] Configuration > Identity. Expected: form fields for Device Name, Device ID (read-only after first set), Latitude, Longitude.
2. [ ] Change Device Name from current to `kmax-test-141`. Save. Expected:
       - Audit log `action: "config_identity_update"`.
       - Toast confirmation.
       - Topbar device name updates within 1s.
       - `local.yaml` `device.name: kmax-test-141`.
3. [ ] Change latitude to `40.7128`, longitude to `-74.0060`. Save.
4. [ ] Restart service via Settings > Meshpoint > Restart service. After restart, values persist.
5. [ ] Device ID field is read-only with a "Locked" pill or similar visual indicator.

### Negative paths

- [ ] PUT `/api/config/identity` with empty name -> 400.
- [ ] PUT with invalid lat (>90 or <-90) -> 400.
- [ ] PUT as viewer -> 403.

### Acceptance

- [ ] Persists across restart on `.141` and `.15`.

## 2. Configuration > Radio

**Status:** [ ] Not started  [ ] In progress  [ ] Pass  [ ] Blocked
**Hardware:** `.141` and `.15`

### Functional walkthrough

1. [ ] Configuration > Radio. Expected: region selector (US, EU_868, ANZ, IN, KR, SG_923), custom frequency input, preset chips (LongFast, MediumFast, ShortSlow, etc.), NodeInfo card with preset chips + Send Now.
2. [ ] Change region from US to ANZ. Expected: confirmation modal "Changing region requires a service restart. Continue?" Click Continue.
3. [ ] Service restarts; concentrator reinitializes with new region. Verify in Radio (status) tab that frequency now reflects ANZ.
4. [ ] Audit log `action: "config_radio_update"`.
5. [ ] Change to a custom frequency (e.g. 906.875 MHz). Save. Expected: applied.
6. [ ] Change preset to ShortSlow. Save. Expected: applied (no restart needed if region unchanged).
7. [ ] Change NodeInfo broadcast interval to 6h. Save. Expected: applied without restart, hot-reload.
8. [ ] Click Send Now. Expected: NodeInfo TX fires immediately.

### Acceptance

- [ ] All controls round-trip to `local.yaml` and persist.
- [ ] Existing `tests/test_nodeinfo_broadcaster.py::TestNodeInfoBroadcasterHotReload` still passes.

## 3. Configuration > Channels

**Status:** [ ] Not started  [ ] In progress  [ ] Pass  [ ] Blocked
**Hardware:** `.141` and `.15`

### Functional walkthrough

1. [ ] Configuration > Channels. Expected: list of existing PSK channels, each row showing channel name and the masked key (last 4 chars only, e.g. `••••••••••••W3Pq`).
2. [ ] Default channel ("LongFast" or whatever the active is) listed.
3. [ ] Click Add channel. Form: name, base64 key (with a "Decode/preview" helper).
4. [ ] Enter name `private-1`, valid base64 key. Save. Expected:
       - Row appears within 500ms.
       - `meshtastic.channel_keys.private-1` written to `local.yaml`.
       - Audit log `action: "channel_add", params: {name: "private-1"}` (NO key in params).
       - `CryptoService` soft-reloads; new key is active without restart.
5. [ ] Click the masked key on the new row. Expected: "Reveal key" prompt asking for current admin password (fresh challenge).
6. [ ] Enter wrong password. Expected: "Password incorrect" error, no key revealed.
7. [ ] Enter correct password. Expected: full base64 key shown for 30 seconds, then auto-masks again. Audit log `action: "channel_reveal", params: {name: "private-1"}`.
8. [ ] Click Delete on `private-1`. Confirm modal. Expected: row removed, `local.yaml` updated, audit `action: "channel_delete"`.

### Negative paths

- [ ] PUT `/api/config/channels` with malformed base64 -> 400.
- [ ] PUT with duplicate name -> 409.
- [ ] POST `/api/config/channels/{name}/reveal` without password challenge -> 401.
- [ ] POST reveal as viewer -> 403.
- [ ] Audit log entries do NOT contain the raw key for any channel operation.

### Acceptance

- [ ] Channel CRUD round-trips.
- [ ] Reveal flow requires fresh password.
- [ ] Keys never leak to audit log.

## 4. Configuration > Transmit

**Status:** [ ] Not started  [x] In progress  [ ] Pass  [ ] Blocked
**Hardware:** `.141` (relay save validated 2026-05-19 @ `e64492b`; see [RESULTS.md](RESULTS.md))

### Functional walkthrough

1. [x] Configuration > Transmit. Expected: TX power, max duty, relay enable, relay max/minute fields, Save button visible. *(2026-05-19 .141: form renders; Save visible.)*
2. [ ] Change TX power from 20 to 17 dBm. Save. Expected: `transmit.tx_power: 17` in `local.yaml`, audit log entry.
3. [ ] Toggle relay enable off. Save. Expected: `relay.enabled: false`. Subsequent packet feed shows no relay activity.
4. [ ] Toggle relay enable back on. Save.
5. [ ] Change max_duty_percent. Note the regional default reminder displayed (e.g. "US default 10%, EU 868 default 1%").
6. [x] Change relay max/minute (e.g. 18), Save. Expected: `relay.max_relay_per_minute` in `local.yaml`. *(2026-05-19 .141: API + UI + yaml verified; restored to 20 after test.)*

### Acceptance

- [x] Persists across restart. *(2026-05-19 .141: relay rate 18 survived restart_service.)*
- [x] Existing `tests/test_duty_cycle_resolver.py` still passes. *(670 pytest pass on tree @ `e64492b`.)*
- [x] Relay settings round-trip via `PUT /api/config/transmit` and `GET /api/config` `transmit.relay`. *(2026-05-19; fix in `e64492b`.)*

## 5. Configuration > MQTT

**Status:** [ ] Not started  [ ] In progress  [ ] Pass  [ ] Blocked
**Hardware:** `.141` and `.15`

### Functional walkthrough

1. [ ] Configuration > MQTT. Expected: enable toggle, broker host, broker port, topic root, region segment, encrypted toggle, gateway ID.
2. [ ] Toggle MQTT enable on. Set broker host `mqtt.meshtastic.org`, port 1883.
3. [ ] Set topic root `msh`, region `US`, gateway ID auto-derived from device ID. Save. Expected:
       - Live preview field below shows `msh/US/2/e/<channel>/<gateway>`.
       - `local.yaml` `mqtt.*` written.
       - Audit log `action: "config_mqtt_update"`.
       - Service log shows "MQTT topic prefix resolved: msh/US/2/e/<channel>/<gateway>".
4. [ ] Add a sub-region segment to topic_root: `msh/US/FL`. Live preview updates.
5. [ ] Toggle MQTT off. Save. Expected: `mqtt.enabled: false`, no service restart needed.

### Negative paths

- [ ] PUT with invalid broker port (0 or > 65535) -> 400.
- [ ] PUT with empty topic_root -> 400.
- [ ] As viewer -> 403.

### Acceptance

- [ ] MQTT round-trips, topic preview live, hierarchical paths work.
- [ ] `tests/test_mqtt_topic_paths.py` (cherry-picked from PR #35) still passes.

## 6. Configuration > GPS

**Status:** [ ] Not started  [ ] In progress  [ ] Pass  [ ] Blocked
**Hardware:** `.141`

### Functional walkthrough

1. [ ] Configuration > GPS. Expected: source toggle (UART vs Static), baud rate input, timeout input, gpsd integration card with "Coming in v0.7.5" placeholder. See `docs/plans/v0.7.5-release.md`.
2. [ ] Toggle source to Static. Latitude and Longitude fields surface (linked to Identity).
3. [ ] Toggle source to UART. Baud rate and timeout fields surface, defaults preserved.
4. [ ] Save. Expected: `gps.source` written to `local.yaml`, audit log entry.
5. [ ] gpsd card has clear "Not yet supported" copy with a link to v0.7.5 release notes (when available).

### Acceptance

- [ ] GPS source toggle works.
- [ ] gpsd placeholder is honest (does not claim functionality).

## 7. Configuration > MeshCore

**Status:** [ ] Not started  [ ] In progress  [ ] Pass  [ ] Blocked
**Hardware:** `.141` (USB companion required for online steps)

### Functional walkthrough

1. [ ] Configuration > MeshCore. Expected: **USB capture source** card (enable, auto-detect, pinned port, baud) and **MeshCore Companion** card when companion connected.
2. [ ] With companion connected: readouts show name, frequency, SF, TX power (not all `?`).
3. [ ] Edit or add one MeshCore channel key (hex), Save Channels. Refresh page; row persists.
4. [ ] **Send Advert** → toast success; journal shows advert sent.
5. [ ] **Refresh** → `GET /api/config` updates; contact roster enrichment within ~30s after boot (see RESULTS `0fb4f4f`).
6. [ ] Save USB source toggle (e.g. auto-detect on). Expected: restart required toast if `restart_required`; service comes back with companion reattached.
7. [ ] Top bar **MeshCore chip** matches companion name + channel after save.

### Acceptance

- [ ] Companion path works end-to-end on `.141`.
- [ ] No Meshradar nav item in sidebar (upstream remains yaml/wizard only).

## 8. Configuration role gate (cross-section)

**Status:** [ ] Not started  [ ] In progress  [ ] Pass  [ ] Blocked
**Hardware:** browser-only via `.15` (viewer)

### Functional walkthrough

1. [ ] Log in as viewer on `.15`.
2. [ ] Sidebar shows Configuration group, expanded.
3. [ ] Each subsection shows current values but every form field is disabled or read-only. No Save buttons.
4. [ ] DevTools: `fetch('/api/config/radio', {method: 'PUT', body: ...})` -> 403.
5. [ ] DevTools: `fetch('/api/config/channels/test/reveal', {method: 'POST', ...})` -> 403.

### Acceptance

- [ ] Viewer cannot mutate Configuration.
- [ ] Viewer can read Configuration values (so they can verify the device is set up correctly).

## Hardware-specific checks

### `.141` (RAK V2)

- [ ] Region change to ANZ + restart succeeds; concentrator re-init produces no errors.
- [ ] Custom frequency 906.875 MHz applies and is reflected in NodeInfo broadcasts.
- [ ] MeshCore USB unaffected by Configuration changes.

### `.15` (SenseCap M1)

- [ ] Region change applies; carrier auto-detection still reports SenseCap M1 in the `Hardware` line of `meshpoint status`.
- [ ] Custom frequency applies cleanly.

## Deferred (not v0.7.4)

- **MQTT broker TLS / mqtts** — Not in v0.7.4 Configuration UI or `mqtt_publisher.py`.
  Plain TCP only (port 1883 for community broker). Bundle with **Meshtastic PKI**
  release; tracked in `docs/CHANGELOG.md` (Unreleased) and `ROADMAP.md`.

## Failure modes to watch

- **Channel reveal returns plaintext without password challenge** — security regression. Halt release.
- **Audit log captures plaintext PSK key** — security regression. Halt release.
- **Region change does not trigger restart prompt** — UX regression. User loses the visual cue that a restart is required.
- **MQTT topic preview is stale** — frontend not re-rendering on input change. Add debounce + re-render hook.
- **Transmit save does not persist after restart** — `save_section_to_yaml` not called for transmit section. Verify route handler.

## Acceptance summary

- [ ] Identity, Radio, Channels, Transmit, MQTT, GPS, and MeshCore pass on `.141`.
- [ ] Identity, Radio, MQTT, role gate verified on `.15`.
- [ ] Audit log entries verified for every mutation; never contain secrets.
- [ ] Sign-off matrix updated in README.md.
