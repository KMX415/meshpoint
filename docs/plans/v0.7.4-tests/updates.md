# Updates — Apply, branch picker, watchdog rollback

Dashboard-driven update apply with release-channel branch picker and Phase 2 watchdog auto-rollback. Replaces the SSH-required `git pull && systemctl restart` flow.

## 1. Update apply — happy path (no-op tag bump)

**Status:** [ ] Not started  [x] In progress  [ ] Pass  [ ] Blocked
**Hardware:** `.141` and `.15`
**Pre-conditions:**
- Logged in as admin
- A test tag pushed to origin newer than the running version
- Test tag introduces no breaking changes (no-op) so we can validate the apply pipeline without risking the unit

### Functional walkthrough

1. [ ] Settings > Updates. Expected: panel renders with three-column header (Installed / Git Branch / Last Checked).
2. [ ] Click "Check for Updates". Expected: spinner briefly, then "Last Checked" updates to "just now", and amber pill "1 available" appears next to "Up to date" status which now reads "Update available: vX.Y.Z".
3. [ ] Click "Apply vX.Y.Z". Expected: streaming modal opens. Steps highlight as they complete:
       - Fetch
       - Checkout
       - Install
       - Restart
       - Watchdog
4. [ ] Final step: green check, "Update complete. New version: vX.Y.Z."
5. [ ] Audit log entry `action: "update_apply", params: {from: "vA", to: "vB"}, result: "success", duration_s: <reasonable>`.
6. [ ] Page auto-reloads. New version visible in topbar / sidebar header.

### Negative paths

- [x] POST `/api/update/apply` without cookie -> 401.
- [x] POST as viewer -> 403.
- [ ] POST while another apply is running -> 409 with `{"detail":"Update already in progress","lock_holder": <user>, "started_at": <iso>}`.

### Acceptance

- [x] Backend chain unit-tested via `_RecorderRunner` test double in `tests/test_update_apply.py` (fetch -> checkout -> pull -> install -> restart, plus failure short-circuit + callback streaming).
- [x] Route-level coverage in `tests/test_update_routes.py` (admin-only, channel resolution, payload shape).
- [ ] Pass on `.141`.
- [ ] Pass on `.15`.

## 2. Branch picker — curated channel switch

**Status:** [ ] Not started  [x] In progress  [ ] Pass  [ ] Blocked
**Hardware:** `.141`

### Functional walkthrough

1. [ ] Settings > Updates > Release Channel section.
2. [ ] See chips: `main` (selected), `dev`, plus any branches listed in `meshpoint-channels.json`.
3. [ ] Click `dev` chip. Expected: confirmation modal "Switch from main to dev? This will pull the dev branch and restart the service."
4. [ ] Click Switch. Expected: streaming modal runs through Fetch / Checkout / Install / Restart / Watchdog steps. Audit log `action: "channel_switch", params: {from: "main", to: "dev"}`.
5. [ ] Page auto-reloads. Git Branch column reads "dev".
6. [ ] Click `main` chip. Expected: same flow, returns to main.

### Acceptance

- [ ] Channel switching round-trips cleanly.

## 3. Branch picker — arbitrary branch (advanced)

**Status:** [ ] Not started  [ ] In progress  [ ] Pass  [ ] Blocked
**Hardware:** `.141`

### Functional walkthrough

1. [ ] Settings > Updates > Release Channel > "Advanced: switch to arbitrary branch...".
2. [ ] Form expands with free-form input, "I know what I'm doing" checkbox, "Switch" button (disabled until both filled).
3. [ ] Enter `feat/v0.7.4-test` (or any real branch). Check the checkbox. Click Switch.
4. [ ] Expected: confirmation modal with bigger warning copy. Click Confirm.
5. [ ] Expected: streaming modal runs; audit log `action: "channel_switch", params: {from: <prev>, to: "feat/v0.7.4-test", arbitrary: true}`.

### Negative paths

- [ ] Enter a branch that does NOT exist on origin. Expected: error toast "Branch not found on origin".
- [ ] Submit without checkbox. Expected: button stays disabled.
- [ ] As viewer, advanced form not visible.

### Acceptance

- [ ] Arbitrary branch path works for valid branches and rejects invalid ones cleanly.

## 4. Update apply — concurrent invocation rejection

**Status:** [ ] Not started  [ ] In progress  [ ] Pass  [ ] Blocked
**Hardware:** `.141`

### Functional walkthrough

1. [ ] In Browser A, click "Apply vX.Y.Z". Streaming modal opens.
2. [ ] Immediately in Browser B (also admin), click "Apply vX.Y.Z". Expected: error toast "Update already in progress (started by kurt at 19:12:30)" with no second apply triggered.

### Negative paths

- [ ] If lock file at `/run/meshpoint/update.lock` is stale (>5 min, no PID alive), it is auto-cleared on next apply request.

### Acceptance

- [ ] Lock file mechanism prevents concurrent applies.
- [ ] Stale lock detection works.

## 5. Watchdog auto-rollback on health failure

**Status:** [ ] Not started  [x] In progress  [ ] Pass  [ ] Blocked
**Hardware:** `.141`
**Pre-conditions:**
- Test branch deliberately broken (e.g. service exits with error or `/api/health` returns 500)

### Functional walkthrough

1. [ ] In a sandbox unit (NOT production), prepare a test branch that intentionally breaks `/api/health`.
2. [ ] From dashboard, switch to the broken branch via the branch picker.
3. [ ] Streaming modal: Fetch / Checkout / Install / Restart all complete.
4. [ ] Watchdog phase begins. Health-poll loop runs; after 3 consecutive failures (60s total), watchdog triggers rollback.
5. [ ] Final modal state: amber warning "Update failed health check. Rolled back to <previous tag>." with audit log entries:
       - `action: "update_apply", result: "rollback_triggered"`.
       - `action: "update_rollback", from: <broken>, to: <previous tag>`.
6. [ ] Service is back on the previous tag. Dashboard reachable.
7. [ ] Pre-update tag `pre-update-<timestamp>` exists in `git tag` listing.

### Negative paths

- [ ] Watchdog only triggers once per apply (one-shot). Manual rollback still possible via terminal.
- [ ] If watchdog itself fails (e.g. `git reset --hard` errors), audit log records the failure clearly.

### Acceptance

- [x] `tests/test_update_watchdog.py` covers healthy-streak success, budget-exhaustion rollback trigger, streak-reset on unhealthy probe, and rollback-handler exception surfacing.
- [ ] Rollback path works on a deliberately-broken test branch.
- [ ] No data loss in `local.yaml` or SQLite during rollback.

## 6. Channel list config (meshpoint-channels.json)

**Status:** [ ] Not started  [ ] In progress  [ ] Pass  [ ] Blocked
**Hardware:** browser-only

### Functional walkthrough

1. [ ] `meshpoint-channels.json` exists at repo root with the schema:
       ```json
       {
         "channels": [
           {"name": "main", "label": "Stable", "description": "..."},
           {"name": "dev", "label": "Pre-release", "description": "..."}
         ]
       }
       ```
2. [ ] After update apply, the dashboard fetches latest copy of this file from the running git worktree.
3. [ ] Branch picker chips reflect the latest channels list.
4. [ ] Adding a new entry to the file (after a release) becomes visible on next dashboard load.

### Acceptance

- [ ] Channels list is data-driven, not hardcoded in JS.

## 7. Update apply — admin-only role gate

**Status:** [ ] Not started  [ ] In progress  [ ] Pass  [ ] Blocked
**Hardware:** `.15` (viewer)

### Functional walkthrough

1. [ ] Log in as viewer on `.15`.
2. [ ] Settings group is not visible in the sidebar at all.
3. [ ] DevTools `fetch('/api/update/check', {method: 'GET'})` -> 403.
4. [ ] DevTools `fetch('/api/update/apply', {method: 'POST'})` -> 403.

### Acceptance

- [ ] Viewer cannot reach update endpoints.

## Hardware-specific checks

### `.141`

- [ ] After an update, MeshCore USB still attached and contacts visible.
- [ ] Concentrator HAL still functional after install.sh re-run.

### `.15`

- [ ] SenseCap M1 carrier auto-detection still passes after update.
- [ ] Concentrator init logs clean post-update.

## Failure modes to watch

- **Update apply hangs at Install step** — `install.sh` taking longer than the WS streaming buffer expects. Increase server-side timeout or make stream chunked progress.
- **Watchdog rolls back too early** — health endpoint slow to start; bump the initial grace period before health polling begins.
- **Pre-update tag not created** — `git tag pre-update-<ts>` missing; check that the apply pipeline runs `git tag` before `git checkout`.
- **Rollback `git reset --hard` fails** — uncommitted changes on the running tree; ensure `git reset --hard HEAD` runs before checkout to clean the tree.
- **Audit log entry missing** — feature wired, audit emitter not invoked. Add a unit test for each branch.

## Acceptance summary

- [ ] All sub-sections pass on `.141`.
- [ ] Sub-sections 1, 7 pass on `.15`.
- [ ] Audit log emission verified for apply, channel_switch, rollback.
- [ ] Sign-off matrix updated in README.md.
