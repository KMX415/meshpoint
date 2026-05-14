# Contributing to Meshpoint

Thanks for your interest in Meshpoint.

This project is still in early alpha, so contributions are welcome, but changes need to stay small, reviewable, and easy to test.

The goal right now is to keep the project stable while it grows.

---

## Basic rules

- Do not push directly to main
- Use a branch + pull request
- Keep PRs focused on one change
- Open an issue first for large changes
- Be clear about what hardware and region you tested on

---

## Good areas to contribute

These are the safest places to help right now:

- Documentation
- Installer / setup scripts
- Dashboard / frontend
- Config validation
- Logging / debugging tools
- Test coverage
- Region support behind flags
- UI polish

---

## High review areas

Changes in these areas may need extra discussion or testing:

- Packet parsing / decoding
- Relay logic
- Transmit behavior
- Radio / concentrator drivers
- Region / frequency plan handling
- Anything that could affect compliance

These are not blocked, just reviewed more carefully.

---

## Workflow

1. Fork the repo
2. Create a branch from main
3. Make your change
4. Test it
5. Open a pull request

Example branch names:

```
feat/eu868-support
fix/install-script
docs/setup
refactor/config-loader
```

---

## Pull request expectations

Include:

- What changed
- Why it changed
- How you tested it
- Hardware used
- Region/frequency plan
- Any risks

If UI/docs only, say so.

If parsing/relay/radio changed, include more detail.

---

## Testing notes

Helpful info:

- Pi model
- Concentrator model
- Attached radio/node
- Frequency plan
- OS version
- Logs / screenshots

Meshpoint interacts with real RF hardware, so testing details matter.

---

## AI-assisted contributions

AI-assisted contributions are allowed.

If you used Claude, ChatGPT, Copilot, etc., mention it in the PR description.

Rules:

- Review the code before submitting
- Do not submit giant AI refactors
- Do not change radio / protocol behavior without testing
- You are responsible for the code, not the AI

---

## Style

- PRs that touch `frontend/` MUST conform to [docs/DESIGN-SYSTEM.md](docs/DESIGN-SYSTEM.md). Read it before opening the PR.
- Keep changes small
- Avoid unrelated cleanup
- Prefer readability
- Comment hardware-specific logic
- Use clear commit messages

---

## Before opening a PR

- Code builds
- Tests pass (if present)
- Docs updated if needed
- Config changes documented
- Hardware/region impact noted
- PR description is clear

---

Meshpoint is evolving quickly. Process will stay simple for now.
