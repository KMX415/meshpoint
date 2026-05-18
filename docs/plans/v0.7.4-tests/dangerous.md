# Dangerous Actions — Restart, Clear DB, Wipe Phantoms, Force NodeInfo, Restart Concentrator

Settings > Dangerous subsection. Every action routes through the shared typed-confirmation modal: the operator types the action's exact label (GitHub-repo-deletion pattern) before the Invoke button activates. The friction is the point -- these are admin endpoints exposed to anyone who phishes a session cookie.

## 1. Restart service (typed-confirmation)

**Status:** [ ] Not started  [x] In progress  [ ] Pass  [ ] Blocked
**Hardware:** `.141`

### Functional walkthrough

1. [ ] Settings > Dangerous. Expected: card layout, one card per action; danger pills graded by stakes.
2. [ ] Restart Service card has description ("Restarts the meshpoint systemd service. Recovers in ~5 seconds.") and an Invoke button.
3. [ ] Click Invoke. Expected: typed-confirmation modal opens. Modal copy lists the action label, the consequence, and a text input with "Type `restart service` to confirm".
4. [ ] Type a wrong value (e.g. `restart`). Confirm button stays disabled.
5. [ ] Type the exact label. Confirm enables. Click Confirm. Expected:
       - Modal closes.
       - Inline status on the card: "Restarting service…" with progress.
       - WS disconnects briefly; reconnects automatically.
       - Inline status updates to "Service restarted." within 10s.
       - Audit log `action: "dangerous.restart_service", result: "success"`.
6. [ ] Page does NOT reload, but live data resumes.

### Acceptance

- [x] Backend tests cover invoke + role gate (`tests/test_dangerous_actions.py`, `tests/test_dangerous_routes.py`).
- [ ] Typed-confirmation flow blocks the action until the label is typed exactly.
- [ ] Inline status feedback present.
- [ ] Audit log entry.

## 2. Restart concentrator (typed-confirmation)

**Status:** [ ] Not started  [ ] In progress  [ ] Pass  [ ] Blocked
**Hardware:** `.141` and `.15`

### Functional walkthrough

1. [ ] Restart Concentrator card with description ("Resets the SX1302 concentrator without full service restart. Recovers in ~3 seconds.").
2. [ ] Click Restart. Expected:
       - Toast "Restarting concentrator..." with progress bar.
       - HAL log lines stream in (visible via terminal or `journalctl`).
       - Toast updates to "Concentrator restarted." within 10s.
       - Audit log `action: "restart_concentrator"`.
3. [ ] Radio (status) tab continues showing live data after concentrator returns.

### Acceptance

- [ ] Concentrator reset without service restart.
- [ ] Toast feedback.
- [ ] Audit log entry.

## 3. Force NodeInfo broadcast (typed-confirmation)

**Status:** [ ] Not started  [ ] In progress  [ ] Pass  [ ] Blocked
**Hardware:** `.141`

### Functional walkthrough

1. [ ] Force NodeInfo Broadcast card with description ("Sends a NodeInfo TX immediately, regardless of countdown.").
2. [ ] Click Send. Expected:
       - Toast "NodeInfo broadcast sent."
       - Radio tab's NodeInfo countdown resets.
       - Audit log `action: "force_nodeinfo_broadcast"`.

### Acceptance

- [ ] One-click send works.
- [ ] Toast and audit confirm.

## 4. Clear local DB (typed-confirmation)

**Status:** [ ] Not started  [ ] In progress  [ ] Pass  [ ] Blocked
**Hardware:** `.141`

### Functional walkthrough

1. [ ] Clear Local DB card with description ("Purges the local SQLite. Cloud retains the historical record. Local data rebuilds within minutes from incoming packets.").
2. [ ] Click Clear. Expected: modal "Are you sure? This will delete all local packets and node history. Cloud data is unaffected." with Cancel / Clear buttons.
3. [ ] Click Cancel. Modal closes, no action.
4. [ ] Click Clear again, then Clear in modal. Expected:
       - Modal closes.
       - Toast "Local DB cleared. Rebuilding from incoming packets."
       - Audit log `action: "clear_local_db"`.
       - Dashboard packet feed and node table now empty.
       - Within minutes, new packets arrive and the tables rebuild.

### Acceptance

- [ ] Modal asks once, no typing required.
- [ ] DB is cleared.
- [ ] Audit log entry.

## 5. Wipe phantom nodes (typed-confirmation)

**Status:** [ ] Not started  [ ] In progress  [ ] Pass  [ ] Blocked
**Hardware:** `.141`

### Functional walkthrough

1. [ ] Wipe Phantom Nodes card with description ("Removes nodes with packet_count = 0 and no identifying fields. Recoverable: nodes that re-broadcast will reappear.").
2. [ ] If there are no phantoms, button is disabled with "No phantoms detected" copy.
3. [ ] If phantoms exist, click Wipe. Expected: modal with phantom count: "Wipe N phantom nodes? This is recoverable."
4. [ ] Click Wipe in modal. Expected:
       - Toast "Wiped N phantom nodes."
       - Audit log `action: "wipe_phantom_nodes", params: {count: N}`.
       - Node table count drops by N immediately.

### Acceptance

- [ ] Phantom detection accurate.
- [ ] Wipe is reversible (real nodes re-broadcast).
- [ ] Audit log entry includes count.

## 6. Dangerous role gate

**Status:** [ ] Not started  [ ] In progress  [ ] Pass  [ ] Blocked
**Hardware:** `.15` (viewer)

### Functional walkthrough

1. [ ] Log in as viewer.
2. [ ] Sidebar Settings group does not show Dangerous subsection at all.
3. [ ] DevTools: `fetch('/api/config/dangerous/restart_service', {method: 'POST'})` -> 403.
4. [ ] DevTools: `fetch('/api/config/dangerous/clear_local_db', {method: 'POST'})` -> 403.

### Acceptance

- [ ] Viewer cannot reach any dangerous action.

## Hardware-specific checks

### `.141`

- [ ] Restart service preserves MeshCore USB attachment.
- [ ] Restart concentrator does NOT detach MeshCore USB.
- [ ] Clear local DB preserves `local.yaml` (config untouched).

### `.15`

- [ ] Restart service preserves SenseCap M1 carrier auto-detection.
- [ ] Restart concentrator works without manual GPIO reset.

## Failure modes to watch

- **Inline status disappears too quickly to read** — auto-dismiss timer too short. 6s minimum, with progress bar.
- **Confirm enables before the typed label matches exactly** — typed-confirmation regression; the input must compare case-sensitive against the action's exact label.
- **Restart service does not actually restart** — endpoint returns 200 but service continues. Check `subprocess.Popen(['systemctl', 'restart', 'meshpoint'])` runs with sudo properly.
- **Clear local DB also wipes config** — destructive bug. Verify endpoint only deletes packet/node tables, not the schema or config file.
- **Wipe phantoms also removes real nodes** — query bug. Phantom criteria must be `packet_count = 0 AND name IS NULL AND short_id IS NULL AND first_seen < <some-floor>`.

## Acceptance summary

- [ ] All five actions pass on `.141`.
- [ ] Restart service + concentrator pass on `.15`.
- [ ] Role gate verified on `.15` (viewer cannot reach).
- [ ] Audit log emission for every action.
- [ ] Sign-off matrix updated in README.md.
