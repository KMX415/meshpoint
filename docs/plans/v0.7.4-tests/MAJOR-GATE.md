# v0.7.4 — Major gate (`.141` first)

Trimmed checklist for **ship decisions**. Polish, axe, design recording, keyboard roving, GPS backend, watchdog auto-rollback, and multi-browser matrix can wait for fleet feedback.

**Full matrix:** [README.md](README.md) · **Evidence:** [RESULTS.md](RESULTS.md)

**Pi target:** `feat/v0.7.4` at or after `2a458e5` (Channels PSK column fix).

```bash
cd /opt/meshpoint
sudo git fetch origin
sudo git pull origin feat/v0.7.4
git log -1 --oneline
```

Hard-refresh the dashboard after pull (`Ctrl+Shift+R`). Frontend-only commits do not need `systemctl restart`.

**Parallel terminal (audit):**

```bash
tail -F /opt/meshpoint/data/admin_audit.jsonl
```

---

## Tier 0 — automated (laptop, 2 min)

```powershell
cd C:\Users\kurtu\meshpoint
python -m pytest tests/ -q
$env:MESHPOINT_BASE="http://192.168.0.141:8080"
$env:MESHPOINT_PASSWORD="<admin>"
python scripts/smoke_v074_api.py
```

Expect: suite green, smoke all OK (GPS PUT skipped by design).

---

## Tier 1 — must pass on `.141` before tag (~90–120 min)

Tick boxes here, then copy one RESULTS row per block.

### A. Auth + roles (~25 min)

| Step | Pass? |
|------|-------|
| Settings → Auth: change password (wrong current → error; good current + new ≥8 → success, kicked to `/login`, re-login works) | [ ] |
| Two browsers/sessions: **Sign out everywhere** logs both out | [ ] |
| Optional: create viewer (`setup_viewer` or UI), login viewer, confirm Configuration is read-only and Dangerous/Updates return 403 | [ ] |

API negatives already smoke-passed; this block is **browser trust**.

### B. Configuration editors (~40 min)

| Step | Pass? |
|------|-------|
| **Identity:** change device name + lat/lon, Save, restart service, values persist | [ ] |
| **Radio:** change preset (e.g. MediumSlow), Save; NodeInfo interval + **Send Now**; top bar preset label updates | [ ] |
| **Channels:** table columns align (PSK under PSK); add or edit one channel, Save, refresh page, row persists | [ ] |
| **MQTT:** enable, broker `mqtt.meshtastic.org`, topic preview `msh/US/...`, Save; journal shows MQTT connect + topic prefix (optional: confirm publish on LongFast) | [ ] |
| **Transmit:** toggle relay or duty-related field you care about, Save, survives restart (already partial in RESULTS) | [ ] |
| **GPS:** skip — mark `n/a` for v0.7.4 (no PUT route) | n/a |

### C. In-dashboard updates (~20 min, destructive once)

| Step | Pass? |
|------|-------|
| Settings → Updates: **Check for updates** shows behind/ahead + last checked | [ ] |
| **Apply** on RC channel completes (fetch → install → restart); dashboard returns; version/SHA updated | [ ] |
| After a successful apply: **Roll back last apply** enabled and restores prior SHA (page reload OK) | [ ] |

If `install.sh` SEGV appears but service recovers, log `partial` + continue (known flake).

### D. Web terminal (~10 min)

| Step | Pass? |
|------|-------|
| Terminal → Connect → **CONNECTED** | [ ] |
| Type `pwd` and `whoami` in xterm; sensible output | [ ] |
| Audit shows `terminal.session_start` / command rows | [ ] |

### E. Dashboard + MeshCore (~15 min)

| Step | Pass? |
|------|-------|
| Sidebar: Dashboard, Messages, Stats, Radio (read-only), Terminal, Configuration subpages, Settings — each loads without console errors | [ ] |
| Dashboard: packet feed + map render; no horizontal page scrollbar at 1280px | [ ] |
| Configuration → MeshCore (or companion card): **Refresh** / contact list populates within ~30s after boot | [ ] |
| Native relay | [x] already pass |

---

## Tier 2 — before merge to `main` (not all on `.141`)

| Gate | Minimum |
|------|---------|
| **Fresh SD `.49`** | **Waived for v0.7.4** (no install/wizard delta; `.141` covers `git pull` upgrade path) |
| **`.15` smoke** | **Done** — `feat/v0.7.4` @ `2a458e5`, full API smoke pass (SenseCap / SX1303 path) |

---

## Explicitly deferred (user / follow-up)

Do **not** block v0.7.4 tag on these:

- Foundation §4 arrow-key roving (`g` chords only)
- `polish.md` hover/axe/design recording
- Auth page live radar blips
- Update indicator badges 12–14 (needs newer-than-local `main`)
- Real phone + landscape sidebar
- GPS editor backend
- Watchdog auto-rollback on failed apply
- Dangerous clear DB / wipe phantoms (unless you need them)
- Spectral scan §2–9 beyond packet-derived §1
- Full cherry-pick MQTT subscribe from external client
- `.15` / browser matrix spot-check every browser

---

## When Tier 1 is green

1. Append RESULTS rows for A–E.
2. Update README matrix `.141` column to `[x]` for rows you fully completed (or `n/a` for GPS / watchdog).
3. Version bump + CHANGELOG fold + merge `feat/v0.7.4` → `main`.
4. `.49` fresh SD not required this RC (see RESULTS Priority B).
