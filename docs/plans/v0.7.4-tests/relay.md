# Smart Relay — native onboard SX1302 (identity-preserving)

The relay subsystem ticked a "relayed" counter for years without
anything actually landing on the air. v0.7.4 wires a real backend
through the onboard concentrator, preserves the original sender's
identity (`source_id`, `packet_id`, `channel_hash`, encrypted body
all survive — only `hop_limit` decrements), and shares the duty-
cycle budget with outbound messaging so relay traffic can never
crowd out user TX.

No second radio required.

## 1. Relay — first-time enable

**Status:** [ ] Not started  [x] In progress  [ ] Pass  [ ] Blocked
**Hardware:** `.141` (RAK V2) and `.15` (SenseCap M1)
**Pre-conditions:**
- Logged in as admin
- Service running v0.7.4 RC
- `transmit.enabled: true` already set (dashboard messaging works)
- At least one Meshtastic node within RX range, RSSI between
  -110 and -50 dBm, broadcasting on a channel the Meshpoint can
  decrypt (LongFast or a configured PSK)

### Backend coverage already green

- [x] `tests/test_native_relay.py::TestNativeRelay` — hop_limit
      decrement preserving `hop_start`, zero-hop refusal, short-
      packet refusal, source/packet ID preservation, duty-cycle
      block, disabled-meshtastic guard.
- [x] `tests/test_native_relay.py::TestRelayManagerAsyncDispatch`
      — async transmit functions are awaited, sync ones run via
      `asyncio.to_thread`.
- [x] `tests/test_meshtastic_transmitter_relay.py::TestRelayPositivePath`
      — legacy USB-companion path for users who still have a
      second radio attached.

### Functional walkthrough

1. [ ] Open `/opt/meshpoint/config/local.yaml`. Add (or edit) the
   `relay:` block:
   ```yaml
   relay:
     enabled: true
     max_relay_per_minute: 20
     burst_size: 5
     min_relay_rssi: -110.0
     max_relay_rssi: -50.0
     # serial_port intentionally omitted — uses the onboard SX1302
   ```
2. [ ] `sudo systemctl restart meshpoint`.
3. [ ] `sudo journalctl -u meshpoint -n 80 --no-pager | grep -E "RELAY|Relay backend"`.
   Expected lines:
   ```
   coordinator:  -- RELAY    native onboard SX1302  max 20/min
   server: Relay backend: native onboard SX1302 (identity-preserving)
   ```
4. [ ] If you instead see `RELAY    USB-companion ready` — `transmit.enabled` is false in your yaml; fix it.
5. [ ] If you see `Relay enabled but no transmit backend available` — both `transmit.enabled` and `relay.serial_port` are unset; pick one.

### Acceptance

- [ ] Startup banner reads "native onboard SX1302" on `.141`.
- [ ] Startup banner reads "native onboard SX1302" on `.15`.

## 2. Relay — first packet on the air

**Status:** [ ] Not started  [ ] In progress  [ ] Pass  [ ] Blocked
**Hardware:** `.141`

### Functional walkthrough

1. [ ] In one SSH window, tail the relay log:
   ```bash
   sudo journalctl -u meshpoint -f | grep -E "RELAY \[|Relay TX|Relay rejected"
   ```
2. [ ] From a phone running Meshtastic (joined to the same channel,
   within RX range of the Meshpoint), broadcast a TEXT message.
3. [ ] Within ~1 second, two log lines appear:
   ```
   relay_manager: RELAY [meshtastic] <phone_id> -> ffffffff (type=text, rssi=-XX.X)
   tx_service:    Relay TX (native): hops N -> N-1, size=YY, airtime=ZZms
   ```
4. [ ] On a *third* Meshtastic node (one further away, ideally out
   of phone RX range but within Meshpoint range), confirm the
   message arrives, attributed to the original phone sender, with
   `hop_count` one higher than direct.
5. [ ] Repeat with a NODEINFO broadcast (wait or restart the phone).
   Same two-line proof should appear with `type=nodeinfo`.

### Identity preservation check

The whole point of native relay is that other nodes treat the
re-broadcast as a relay rather than a fresh broadcast from the
Meshpoint. Confirm:

- [ ] `source_id` in the relay log matches the original sender's
  4-byte node ID, NOT the Meshpoint's `transmit.node_id`.
- [ ] `packet_id` in the relay log is the original packet's ID
  (visible in the `>> PKT` decode log a few lines above the
  `RELAY` line).
- [ ] On the receiving node, the message attribution is the
  original sender's name, not "Meshpoint".

### Acceptance

- [ ] First TEXT packet relays on `.141` with hop decrement.
- [ ] First NODEINFO packet relays on `.141` with hop decrement.
- [ ] Identity preservation confirmed on a receiving node.
- [ ] Same three checks on `.15`.

## 3. Relay — filter coverage

**Status:** [ ] Not started  [ ] In progress  [ ] Pass  [ ] Blocked
**Hardware:** `.141`

The decision engine should reject packets for the right reasons.
Tail `journalctl ... | grep "Relay rejected"` and confirm at
least one occurrence of each reason during a busy 30-minute
window.

- [ ] `signal_too_strong` — packet from a very close neighbour
  (RSSI > -50 dBm). Expected on most setups; the Meshpoint
  shouldn't relay packets that everyone in earshot already heard
  loud and clear.
- [ ] `signal_too_weak` — packet at RSSI < -110 dBm. Rare; only
  triggered by a marginally-decoded packet at the edge of
  sensitivity.
- [ ] `duplicate` — same packet seen twice within the dedup
  window (5 min). Common in dense mesh traffic where multiple
  paths reach the Meshpoint.
- [ ] `non_relayable_type` — packet types not in `{TEXT, POSITION,
  TELEMETRY, NODEINFO}`. ROUTING, ADMIN, TRACEROUTE, etc.
- [ ] `no_hops_remaining` — packet arrived with `hop_limit=0`.
- [ ] `rate_limited` — only fires under heavy traffic. Force by
  temporarily setting `max_relay_per_minute: 2` in yaml,
  restarting, and waiting for a few packets.

### Acceptance

- [ ] All six rejection reasons observed in a real 30-minute
  window (or synthesised via config tweaks for the rare ones).

## 4. Relay — duty cycle interaction

**Status:** [ ] Not started  [ ] In progress  [ ] Pass  [ ] Blocked
**Hardware:** `.141`

Native relay shares the same `DutyCycleTracker` as outbound
messaging, so heavy relay traffic must not crowd out user TX.

### Functional walkthrough

1. [ ] In `local.yaml`, temporarily set
   `transmit.max_duty_cycle_percent: 0.5` (very tight). Restart.
2. [ ] Send a few messages from the dashboard while a busy mesh
   is around. Expected: dashboard messaging eventually shows
   "Duty cycle limit reached" errors, AND `journalctl` shows the
   same error against `Relay TX (native)`.
3. [ ] Restore `max_duty_cycle_percent` to its prior value (or
   omit to use the regional default — 10% US, 1% EU). Restart.
4. [ ] Verify both messaging and relay coexist without the duty
   message under normal load.

### Acceptance

- [ ] Duty exhaustion gates relay before lgw_send is called
  (no airtime spent on rejected relays).
- [ ] Duty exhaustion gates messaging the same way.
- [ ] Default config has neither path hitting the limit under
  normal mesh load on `.141`.

## 5. Relay — encrypted-packet skip

**Status:** [ ] Not started  [ ] In progress  [ ] Pass  [ ] Blocked
**Hardware:** `.141`

Packets the Meshpoint can't decrypt locally (no key match) must
NOT be relayed on the native path — re-emitting opaque bytes
that other nodes can't authenticate is worse than not relaying.

### Functional walkthrough

1. [ ] Identify a node broadcasting on a private channel whose
   PSK is NOT in `meshtastic.channel_keys`. Easy way: have a
   neighbour set up a private channel with a key you don't have.
2. [ ] When that node's packets arrive, the dashboard packet
   feed shows them as `ENCRYPTED` type. Tail the relay log.
3. [ ] Expected: no `RELAY [meshtastic]` line for those packets
   (they fail `non_relayable_type` because `ENCRYPTED` is not
   in the relay-worthy set).
4. [ ] Decrypted packets on a known channel from the same node
   (when present) should still relay normally.

### Acceptance

- [ ] Encrypted packets observed in the packet feed but absent
  from the relay log.

## 6. Relay — legacy USB-companion path (regression)

**Status:** [ ] Not started  [ ] In progress  [ ] Pass  [ ] Blocked
**Hardware:** Optional (only relevant if testing the legacy
path)

If a tester has a second Meshtastic radio attached via USB and
wants the old behaviour, the legacy path still works.

### Functional walkthrough

1. [ ] Disable native: `transmit.enabled: false`.
2. [ ] Configure legacy: `relay.serial_port: /dev/ttyACM1`
   (or wherever the second radio is).
3. [ ] Restart. Banner should read:
   ```
   coordinator:  -- RELAY    USB-companion ready  max 20/min
   ```
   plus a WARNING line explaining that this is the legacy path.
4. [ ] Verify packets relay through the second radio. Note that
   on this path, the relay radio re-broadcasts as ITSELF (not
   identity-preserving). Acceptable for setups that need a
   geographically-separated TX antenna.

### Acceptance

- [ ] Legacy path still works for the one tester who has the
  hardware. Skip otherwise.

## Failure modes to watch

- **`RELAY [meshtastic]` lines but no `Relay TX (native)` follow.**
  Decision engine accepted the packet but `send_raw_relay`
  refused it. Inspect the level-DEBUG log to see whether
  `Native relay TX skipped: <reason>` was emitted.
- **Counter ticks up in dashboard but no log lines.** Means the
  relay function returned silently without an error. Should be
  impossible after the v0.7.4 fix; if it happens, that's a
  regression of the original v0.7.0 bug and should be filed
  immediately.
- **Other nodes show the Meshpoint as the sender on relayed
  packets.** Indicates the legacy USB path is active when the
  native path was expected. Check `transmit.enabled` and the
  startup banner.
- **`lgw_send returned -1` on every relay.** Concentrator wedged
  or another TX is in flight. Check the duty tracker output and
  consider whether `nodeinfo.interval_minutes` or messaging
  cadence is interleaving badly.
