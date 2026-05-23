# Web Terminal — PTY session, command guide drawer, irreversibles confirmation

Full shell, on by default, admin-only. Verifies the terminal session lifecycle, command guide UX, hard limits, and audit emission.

## 1. Terminal — first open and basic command execution

**Status:** [ ] Not started  [x] In progress  [ ] Pass  [ ] Blocked
**Hardware:** `.141` and `.15`
**Pre-conditions:**
- Logged in as admin
- Service running v0.7.4 RC

### Backend coverage already green

- [x] `tests/test_terminal_command_catalog.py` — unique ids, dangerous-flag invariants, JSON payload shape, category ordering.
- [x] `tests/test_terminal_session_manager.py` — cap enforcement, lifecycle, double-close idempotency. Live PtySession tests skip on non-POSIX.
- [x] `tests/test_terminal_routes.py` — admin-only on `/commands` and `/status`, anonymous + viewer rejection.

### Functional walkthrough

1. [ ] Click Terminal in the sidebar. Expected: Terminal section opens, xterm.js renders, sticky session header strip shows `pi@meshpoint-...:/opt/meshpoint`, WS-health pulse dot mint green.
2. [ ] Empty state visible if first open, with welcome glyph + "Press `?` to see available commands or just start typing."
3. [ ] Type `pwd` + Enter. Expected: command echoes, output `/opt/meshpoint` appears within 200ms.
4. [ ] Type `whoami`. Expected: `root` (service runs as root).
5. [ ] Type `meshpoint status`. Expected: status output streams in.
6. [ ] Type `journalctl -u meshpoint -n 5 --no-pager`. Expected: last 5 log lines stream in.
7. [ ] Type `tail -f /var/log/syslog`. Expected: streaming output. Press Ctrl+C. Expected: stream stops, prompt returns.
8. [ ] Use up arrow. Expected: previous command appears at the prompt. Up again. Expected: older command. Down. Expected: forward through history.
9. [ ] Type a long command, press Ctrl+A. Expected: cursor jumps to start of line. Ctrl+E. Expected: end of line.
10. [ ] Highlight some output, copy. Paste into another window. Expected: text matches.

### Acceptance

- [ ] All steps pass on `.141`.
- [ ] All steps pass on `.15`.

## 2. Terminal — command guide drawer

**Status:** [ ] Not started  [ ] In progress  [ ] Pass  [ ] Blocked
**Hardware:** `.141`

### Functional walkthrough

1. [ ] Press `?` while focused in terminal. Expected: drawer slides in from right, 220ms.
2. [ ] Search-as-you-type: type "log". Expected: list filters live to commands containing "log" in name or description.
3. [ ] Click chevron next to `journalctl`. Expected: row expands to show full usage syntax + flags + example invocation + "INSERT AT PROMPT" button.
4. [ ] Click "RUN" on `meshpoint status`. Expected: drawer closes, command appears at prompt, executes, streams output.
5. [ ] Open drawer again, click "INSERT AT PROMPT" on `meshpoint setup`. Expected: drawer closes, command appears at prompt but NOT executed (so user can edit).
6. [ ] Drawer's grouped sections: Service Control, Diagnostics, Updates, Network, Config, Auth, Hardware, Filesystem.
7. [ ] Press `?` again or click outside drawer or press Escape. Expected: drawer closes.

### Acceptance

- [ ] All steps pass.
- [ ] Drawer transitions feel snappy not laggy.

## 3. Terminal — irreversibles confirmation

**Status:** [ ] Not started  [ ] In progress  [ ] Pass  [ ] Blocked
**Hardware:** `.141`

### Functional walkthrough

1. [ ] Type `rm -rf /tmp/test-no-such-dir`. Expected: confirmation modal appears: "This command is irreversible. Are you sure you want to run: `rm -rf /tmp/test-no-such-dir`?" with "Cancel" / "Run" buttons.
2. [ ] Click Cancel. Expected: modal closes, command does not execute.
3. [ ] Type same command, click Run. Expected: command runs, "No such file or directory" error from rm.
4. [ ] Type `dd if=/dev/zero of=/tmp/test bs=1M count=1`. Expected: confirmation modal triggers (matches `dd if=`).
5. [ ] Append `--yes-i-know` flag: `dd if=/dev/zero of=/tmp/test bs=1M count=1 --yes-i-know`. Expected: NO modal, command runs.
6. [ ] Type `mkfs.ext4 /dev/null`. Expected: confirmation modal triggers.

### Negative paths

- [ ] Modal does NOT trigger on benign commands containing "rm" or "dd" substrings (e.g. `du -sh`, `apt-get install dd`).
- [ ] Modal pattern matches the start-of-token, not arbitrary substrings.

### Acceptance

- [ ] Pass on `.141`.

## 4. Terminal — audit log emission

**Status:** [ ] Not started  [ ] In progress  [ ] Pass  [ ] Blocked
**Hardware:** `.141`

### Functional walkthrough

1. [ ] In another SSH session, `sudo tail -F /opt/meshpoint/data/admin_audit.jsonl`.
2. [ ] In dashboard terminal, type `echo hello` + Enter. Expected: audit row `action: "terminal_command", params: {command: "echo hello"}, result: "success"`.
3. [ ] Type `false` + Enter. Expected: audit row with non-zero exit code (best-effort parsed from prompt or exit code).
4. [ ] Type a long-running command (e.g. `sleep 3`) + Enter. Expected: audit row written when command completes, not when started.

### Negative paths

- [ ] Multi-line input (e.g. heredoc) recorded as one logical command in the audit log, not per-line.
- [ ] Audit log doesn't capture interactive prompt responses (e.g. `sudo apt install`'s "Y/N" prompts).

### Acceptance

- [ ] Every command line submitted to PTY is logged exactly once.

## 5. Terminal — admin-only role gate

**Status:** [ ] Not started  [ ] In progress  [ ] Pass  [ ] Blocked
**Hardware:** `.15` (viewer-role unit)

### Functional walkthrough

1. [ ] Log in as viewer on `.15`.
2. [ ] Sidebar does not show Terminal item. Expected.
3. [ ] In DevTools, attempt `new WebSocket('ws://<dashboard-host>:8080/api/terminal/ws')` with viewer cookie. Expected: server calls `accept()` then `close(code=4401)` (or 4403 if viewer-detected). Browser receives close code, no PTY allocated.
4. [ ] In DevTools, attempt `fetch('/api/terminal/commands')`. Expected: 403.

### Acceptance

- [ ] Viewer cannot reach terminal at all.

## 6. Terminal — concurrent session limit

**Status:** [ ] Not started  [ ] In progress  [ ] Pass  [ ] Blocked
**Hardware:** `.141`

### Functional walkthrough

1. [ ] Open 5 browser tabs to the dashboard, all logged in as admin.
2. [ ] Open Terminal in each. Expected: 5 sessions allocate, each with its own PTY.
3. [ ] Open a 6th tab, navigate to Terminal. Expected: error toast "Maximum concurrent sessions (5) reached. Close another terminal to open a new one."
4. [ ] Close one of the 5 tabs. Expected: PTY cleaned up server-side within 5s.
5. [ ] In 6th tab, retry. Expected: now succeeds.

### Acceptance

- [ ] Limit enforced server-side, not just client-side.

## 7. Terminal — idle disconnect

**Status:** [ ] Not started  [ ] In progress  [ ] Pass  [ ] Blocked
**Hardware:** `.141`

### Functional walkthrough

1. [ ] Open Terminal. Run a command. Wait 10 minutes with no input.
2. [ ] Expected: WS closes with idle-timeout reason. Banner appears "Terminal session disconnected (idle). Click to reconnect."
3. [ ] Click. Expected: new PTY allocated, prompt visible.

### Acceptance

- [ ] Idle disconnect fires on schedule.
- [ ] Reconnect path works.

## 8. Terminal — output limits and stream backpressure

**Status:** [ ] Not started  [ ] In progress  [ ] Pass  [ ] Blocked
**Hardware:** `.141`

### Functional walkthrough

1. [ ] Run `yes | head -n 100000`. Expected: output streams at a paced rate, browser remains responsive.
2. [ ] Run a command that produces > 1 MB of output (e.g. `cat /var/log/syslog` if large). Expected: output streams up to the per-command limit, then notice appears: "Output truncated at 1 MB. See file directly for full content."
3. [ ] Browser memory does not balloon (check Task Manager).

### Acceptance

- [ ] Output limit enforced.
- [ ] Browser stays responsive.

## Hardware-specific checks

### `.141` (RAK V2)

- [ ] Terminal accepts MeshCore CLI commands without breaking the USB attachment (e.g. `meshpoint meshcore` does not detach the companion).

### `.15` (SenseCap M1)

- [ ] Terminal accepts SenseCap-specific paths (e.g. `i2cdetect -y 7` shows the 0x60 ATECC608).

## Failure modes to watch

- **PTY session hangs on `tail -f`** — Ctrl+C not propagating through the WS protocol. Check that `{type: "input", data: "\x03"}` reaches the PTY.
- **Browser shows close code 1006 on viewer attempt** — `accept()` not called before `close(4401)`; same regression class as v0.7.3.1 hotfix.
- **Memory leak after multiple sessions** — PTY processes not cleaned up on WS close; verify `terminal_session.cleanup` runs on disconnect.
- **Audit log captures interactive prompt responses** — should not. Only the command line submitted to the prompt is audited; sudo password input or interactive Y/N prompts are not captured.
- **Drawer doesn't render on phone** — slide-in animation broken at narrow widths. Check media queries.

## Acceptance summary

- [ ] All sub-sections pass on `.141`.
- [ ] Sub-sections 1, 5 pass on `.15` (full walkthrough on `.15` covers PTY + role gate).
- [ ] Audit log emission verified for every command path.
- [ ] Sign-off matrix updated in README.md.
