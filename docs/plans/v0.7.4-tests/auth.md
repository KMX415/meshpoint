# Auth — Password change, viewer role, sign-out-everywhere, configurable lockout

Auth completeness work. Builds on v0.7.3 auth foundation.

## 1. Password change UI

**Status:** [ ] Not started  [x] In progress  [ ] Pass  [ ] Blocked
**Hardware:** `.141` and `.15`, plus browser-only role gate verification
**Pre-conditions:**
- Logged in as admin
- Admin password is the current value (you know it)

### Functional walkthrough

1. [ ] Navigate to Settings > Auth.
2. [ ] Locate "Change password" card. Three fields: Current password, New password, Confirm new password.
3. [ ] Enter wrong current password. Click Save. Expected: form shows "Current password incorrect" inline error, no request beyond a single 401 from `/api/auth/change_password`.
4. [ ] Enter correct current password, mismatched new+confirm. Expected: inline "Passwords do not match" error before any request fires.
5. [ ] Enter correct current, matching new (7 chars). Expected: client-side validation rejects with "Password must be at least 8 characters."
6. [ ] Enter correct current, matching new (>= 8 chars). Click Save. Expected:
       - Audit log entry `action: "password_change", result: "success"`.
       - Toast "Password updated. Re-authenticating..."
       - Browser redirects to `/login` after 401 on next API call (jwt_secret rotated).
7. [ ] Log in with the new password. Expected: success, redirected to dashboard.
8. [ ] Old password no longer works.

### Negative paths

- [x] POST `/api/auth/change_password` without cookie -> 401.
- [ ] POST as viewer with valid viewer cookie + valid current viewer password -> 200 (viewers may change their own password).
- [x] POST with wrong current_password -> 401 with `{"detail":"invalid_current_password"}`.
- [x] POST with new_password length < 8 -> 400.
- [ ] POST during rate-limited window -> 429 with Retry-After.

### Acceptance

- [ ] Pass on `.141` and `.15`.
- [x] Test `tests/test_auth_routes_v074.py` covers route paths; `tests/test_auth_service_v074.py` covers service.
- [x] Audit log entry written on success (`action: "auth.change_password"`).

## 2. Sign out everywhere

**Status:** [ ] Not started  [x] In progress  [ ] Pass  [ ] Blocked
**Hardware:** `.141`, plus a second browser session for verification
**Pre-conditions:**
- Logged in as admin in two browsers (or two devices)

### Functional walkthrough

1. [ ] In Browser A, navigate to Settings > Auth > Sign out everywhere.
2. [ ] See the warning copy: "This will sign out every browser including this one."
3. [ ] Click "Sign out everywhere". Expected:
       - Audit log entry `action: "logout_all", result: "success"`.
       - Browser A redirects to `/login`.
4. [ ] In Browser B, perform any authenticated action (click a sidebar item that triggers an API call). Expected: 401, redirected to `/login`.
5. [ ] Log in as admin again in Browser A. Expected: success.
6. [ ] Browser B requires login too. Expected: success on its own login flow.

### Negative paths

- [x] POST `/api/auth/logout_all` without cookie -> 401.
- [x] POST as viewer -> 403 (this is admin-only because it affects all sessions).
- [x] After a successful logout_all, the old JWT cookie value cannot be reused (session_version mismatch).

### Acceptance

- [ ] Pass on `.141`.
- [x] Tests `tests/test_auth_routes_v074.py::TestLogoutAllRoute` cover route + role enforcement.
- [x] Audit log entry written (`action: "auth.logout_all"`).

## 3. Configurable lockout from dashboard

**Status:** [ ] Not started  [x] In progress  [ ] Pass  [ ] Blocked
**Hardware:** `.141` and `.15`

### Functional walkthrough

1. [ ] Settings > Auth > Lockout configuration card.
2. [ ] See current values: lockout_attempts (default 5), lockout_cooldown_minutes (default 5).
3. [ ] Change lockout_attempts to 3. Save. Expected:
       - Audit log entry `action: "lockout_config_update"`.
       - Toast confirmation.
4. [ ] Open `/login` in a private window. Enter wrong password 3 times. Expected: locked out, countdown shows minutes remaining.
5. [ ] Wait for cooldown to expire. Expected: lock clears, login succeeds with correct password.
6. [ ] Set lockout_attempts to 100. Save. Confirms the upper bound accepts.

### Negative paths

- [x] PUT `/api/config/auth_lockout` with `lockout_attempts: 0` -> 422 (range validated by pydantic).
- [ ] PUT with `lockout_attempts: 101` -> 422 (must be <= 100).
- [ ] PUT with `lockout_cooldown_minutes: 0` -> 422 (must be >= 1).
- [ ] PUT with `lockout_cooldown_minutes: 1441` -> 422 (must be <= 1440).
- [ ] PUT without cookie -> 401.
- [ ] PUT as viewer -> 403.

### Acceptance

- [ ] Pass on `.141`.
- [x] `tests/test_auth_routes_v074.py::TestAuthLockoutConfigRoute` and `tests/test_auth_service_v074.py::TestUpdateLockoutConfig` cover service + route.

## 4. Viewer role end-to-end

**Status:** [ ] Not started  [x] In progress  [ ] Pass  [ ] Blocked
**Hardware:** `.141` (admin setup) and `.15` (viewer login verification)
**Pre-conditions:**
- Admin account active on `.141`

### Functional walkthrough — admin setup

1. [ ] Settings > Auth > Viewer access card.
2. [ ] Toggle "Enable viewer role". Form expands to "Set viewer password".
3. [ ] Enter viewer password (>= 8 chars). Save. Expected:
       - `web_auth.viewer_password_hash` written to `local.yaml`.
       - `web_auth.allow_read_only: true`.
       - Audit log `action: "viewer_setup"`.
4. [ ] Navigate to Settings > Auth, the card now shows "Viewer access enabled" with "Disable" / "Change password" / "Reveal username" options.

### Functional walkthrough — viewer login on `.15`

5. [ ] On `.15`, open `http://<dashboard-host>:8080/login` in a private window.
6. [ ] Enter username `viewer`, viewer password. Expected: redirected to dashboard.
7. [ ] Topbar / sidebar role pill reads "Viewer".
8. [ ] Sidebar items visible to viewer: Dashboard, Stats, Messages, Radio. Configuration group: read-only listing of subsections (no Save buttons inside).
9. [ ] Sidebar items hidden from viewer: Terminal, Settings (entire group).
10. [ ] Attempt to type into any Configuration field. Expected: fields are disabled or absent.
11. [ ] Open browser DevTools, attempt `fetch('/api/terminal/ws')`. Expected: 403.
12. [ ] Attempt `fetch('/api/auth/change_password', {method: 'POST', ...})`. Expected: 200 (viewers can change their own password).
13. [ ] Attempt `fetch('/api/config/dangerous/restart_service', {method: 'POST'})`. Expected: 403.
14. [ ] Attempt `fetch('/api/update/apply', {method: 'POST'})`. Expected: 403.

### Negative paths

- [x] `GET /api/identity` for viewer returns `available_sections` array WITHOUT `terminal`, `settings.dangerous`, `settings.updates`.
- [x] `GET /api/identity` for admin returns `available_sections` array WITH all sections.
- [x] Viewer attempting `POST /api/auth/logout_all` -> 403.

### Hardware-specific checks

- [ ] On `.15`, viewer login works with the same cookie pattern as admin (same `auth_session` cookie name, just different role claim).

### Acceptance

- [ ] Admin can set viewer password on `.141`.
- [ ] Viewer can log in on `.15` and sees only viewer-allowed sections.
- [ ] All admin-only endpoints return 403 for viewer.
- [ ] `tests/test_viewer_role_e2e.py` covers all role gating.

## Failure modes to watch

- **Password change appears to succeed but old password still works** — `jwt_secret` not rotated; check `complete_password_change` writes new secret to `local.yaml` AND in-memory.
- **logout_all doesn't kick other browsers** — `session_version` not bumped or not enforced in JWT validation. Check `JwtSessionService.validate` checks the version claim.
- **Lockout count doesn't reset after cooldown** — in-memory tracker not aging entries; check `LockoutTracker.purge_expired` runs.
- **Viewer sees Terminal in sidebar** — `available_sections` not filtered; check `IdentityService.build_response` for role-aware filtering.
- **Viewer 403 on `/api/identity` itself** — guard misconfigured. `/api/identity` should be `Depends(require_auth)`, not `require_admin`.

## Acceptance summary

- [ ] All four features pass on `.141` (admin setup paths).
- [ ] Viewer login + role enforcement passes on `.15`.
- [ ] All audit log entries write correctly.
- [ ] Sign-off matrix updated in README.md.
