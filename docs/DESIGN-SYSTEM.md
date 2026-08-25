# Design System

This is the canonical visual style guide for the Meshpoint local
dashboard (`frontend/`). Read it before opening any pull request that
touches `frontend/`. Every PR that adds or changes UI code is
reviewed against this document.

Scope of this guide is the Meshpoint local dashboard only. The
Meshradar cloud dashboard has its own (separate) design system.

---

## Brand Identity

UI strings, page titles, and any user-visible prose must follow the
Meshpoint brand rules:

- The device is **Meshpoint**: one word, capital M. Never
  "Mesh Point", "MeshPoint", or "mesh point".
- The platform is **Meshradar**: one word, capital M. Never
  "Mesh Radar", "MeshRadar", or "mesh radar".
- Plurals are **Meshpoints** and **Meshradars**.
- USB Meshtastic and MeshCore radios are **nodes**, never **sticks**.
  Say "USB node", "Meshtastic USB node", or "MeshCore companion".
  GPS dongles may still be called USB sticks.
- Code identifiers (CSS class names, JS variables, config keys) keep
  existing project conventions (`top-bar`, `meshpoint`, `mesh_point`).
  The branding rule applies to prose, docs, UI strings, and
  user-facing text only.

Writing style for UI copy:

- Never use em dashes (`—`). Use a colon (`:`) or rewrite the sentence.
- Never use en dashes (`–`) as punctuation. Use a colon or rewrite.
- Hyphens (`-`) are fine for compound words.

Page `<title>` rule:

- The `<title>` should read `Meshpoint Dashboard` (or a similarly
  Meshpoint-branded short string). It must not introduce a new
  tagline or marketing line.

---

## Color Tokens

The canonical token palette lives in `frontend/css/dashboard.css`
in the `:root` block. New CSS in `frontend/` MUST use these tokens
and MUST NOT redeclare or rename them.

### Backgrounds

| Token | Value | Usage |
|---|---|---|
| `--bg-primary` | `#0a0e17` | Page background, deep base |
| `--bg-secondary` | `#111827` | Top bar, table headers, packet detail rows |
| `--bg-card` | `#162033` | Stat cards, drawer header, control surfaces |
| `--bg-glass` | `rgba(22, 32, 51, 0.7)` | Panel surfaces (with `backdrop-filter: blur(12px)`) |

### Borders

| Token | Value | Usage |
|---|---|---|
| `--border` | `#233049` | All static borders |
| `--border-glow` | `rgba(6, 182, 212, 0.2)` | Hover borders on `.panel` |

### Text

| Token | Value | Usage |
|---|---|---|
| `--text-primary` | `#e2e8f0` | Body copy, headings, strong values |
| `--text-secondary` | `#94a3b8` | Secondary copy, table cells |
| `--text-muted` | `#64748b` | Labels, hints, captions, meta |

### Accents

| Token | Value | Usage |
|---|---|---|
| `--accent-cyan` | `#06b6d4` | Primary accent, hover, focus, mono numerics |
| `--accent-green` | `#00e5a0` | Success, online, active device, relay stats |
| `--accent-blue` | `#3b82f6` | Meshtastic protocol indicator |
| `--accent-purple` | `#a855f7` | Meshcore protocol indicator |
| `--accent-amber` | `#f59e0b` | Warnings, position packets, update badge |
| `--accent-red` | `#ef4444` | Errors, encrypted packets, disconnected status |

### Effects and shape

| Token | Value | Usage |
|---|---|---|
| `--glow-cyan` | `0 0 8px rgba(6, 182, 212, 0.3)` | Cyan glow halo (focus, active accents) |
| `--glow-green` | `0 0 8px rgba(0, 229, 160, 0.4)` | Green glow (healthy / OK status lamps) |
| `--glow-amber` | `0 0 8px rgba(245, 158, 11, 0.4)` | Amber glow (warning / caution status) |
| `--glow-red` | `0 0 8px rgba(239, 68, 68, 0.4)` | Red glow (error / paused status) |
| `--radius` | `8px` | Default corner radius for cards, panels, inputs |
| `--radius-sm` | `4px` | Small inputs, chips, narrow buttons |

---

## Semantic Color Mapping

These mappings already exist across the dashboard. New code that
expresses the same concepts MUST reuse them rather than invent new
mappings.

### Protocol colors

| Protocol | Token |
|---|---|
| Meshtastic | `--accent-blue` |
| Meshcore | `--accent-purple` |

### Packet type colors

Lifted from `frontend/css/dashboard.css` (`.packet-table td.type-*`).

| Packet type | Token |
|---|---|
| `text` | `--accent-green` |
| `position` | `--accent-amber` |
| `telemetry` | `--accent-cyan` |
| `nodeinfo` | `--accent-purple` |
| `encrypted` | `--accent-red` |
| `routing` | `--text-muted` |
| `traceroute` | `--accent-blue` |
| `neighborinfo` | `--accent-blue` |

### RSSI buckets

Used in the packet table cells.

| Bucket | Token |
|---|---|
| `rssi-good` | `--accent-green` |
| `rssi-mid` | `--accent-amber` |
| `rssi-bad` | `--accent-red` |

### Signal-quality buckets

Used in node card chips and messaging signal indicators. These are
currently hardcoded hex (legacy), but the SEMANTIC mapping is
canonical and MUST be preserved on any new component that displays
signal quality.

| Bucket | Hex | Notes |
|---|---|---|
| `excellent` | `#00e676` | Brighter than `--accent-green`, kept for visual contrast in chip context |
| `good` | `#4ecdc4` | Legacy teal, slightly different from `--accent-cyan` |
| `fair` | `#ffd54f` | Legacy yellow |
| `poor` | `#ff5252` | Legacy red |

A future cleanup PR will migrate these to tokens. Do not introduce
NEW hardcoded colors; reuse one of these four if you need a quality
bucket on a new component.

---

## Typography

Two font families are loaded from Google Fonts in `frontend/index.html`.
Do not introduce additional font families.

| Token | Family | Usage |
|---|---|---|
| `--font-sans` | `Inter` (with system fallback) | All prose: body, headings, labels, buttons |
| `--font-mono` | `JetBrains Mono` (with `Fira Code` fallback) | Numerics, IDs, hashes, packet data, signal values, table cells |

### Type scale (existing canonical sizes)

| Surface | Size | Weight | Casing |
|---|---|---|---|
| Top-bar `<h1>` | `1.05rem` | 600 | mixed |
| Top-bar status | `0.8rem` mono | 600 (stats), 400 (label) | mixed |
| Tab button | `0.85rem` | 500 | mixed |
| Panel header | `0.7rem` | 600 | UPPERCASE, `0.05em` letter-spacing |
| Stat card label | `0.6rem` | normal | UPPERCASE, `0.05em` letter-spacing |
| Stat card value | `1.1rem` mono | 700 | mixed |
| Packet table header | `0.7rem` mono | 600 | UPPERCASE, `0.04em` letter-spacing |
| Packet table cell | `0.78rem` mono | 400 | mixed |
| Node card name | `0.8rem` | 600 | mixed |
| Node card chip | `0.6rem` mono | 600-700 | mixed (or UPPERCASE for quality) |

When in doubt, match the size and weight of an existing surface that
plays the same role.

---

## Layout Primitives

The dashboard uses one shell pattern and a small set of container
primitives. New work composes these. A change to the shell (for
example, replacing the tab bar with a sidebar) is a design RFC, not
a regular PR.

### Shell

```
<header class="top-bar"> ... </header>
<nav class="tab-bar"> ... </nav>
<div id="tab-X" class="tab-content tab-content--active"> ... </div>
<div id="tab-Y" class="tab-content"> ... </div>
```

The top bar is sticky (`position: sticky; top: 0; z-index: 1000`).
The tab bar is a single-row horizontal strip with one
`tab-bar__btn--active` at a time. Each tab body is a
`.tab-content` div, only the active one is shown.

### `.panel`

The single canonical container for any rectangular content surface.

```
<div class="panel">
  <div class="panel__header">Title</div>
  <div class="panel__body"> ... </div>
</div>
```

Backed by `--bg-glass` with `backdrop-filter: blur(12px)`,
`--border`, and `--radius`. Hover state lifts the border to
`--border-glow`.

### `.stat-card`

Small horizontal cards in a horizontally-scrollable strip
(`.dashboard__stats`). Each card has a label, a large mono value,
and an optional sub-line. Modifiers (`.stat-card--relay`,
`.stat-card--system`) tint the border and value color to convey
category.

### Drawer (right-side slide-in)

```
<div id="X-backdrop" class="nd-backdrop"></div>
<div id="X-drawer" class="nd-drawer"> ... </div>
```

Used for node detail today. Right-side, ~50% width, with a backdrop
overlay. Reuse this primitive for any future detail-view that does
not deserve its own tab.

---

## Naming Convention

All CSS class names follow **BEM**:

- `block` for the component root: `top-bar`, `panel`, `stat-card`
- `block__element` for a child of the block: `top-bar__brand`,
  `panel__header`, `stat-card__value`
- `block--modifier` for a state or variant: `tab-bar__btn--active`,
  `stat-card--relay`, `nc-chip--excellent`
- kebab-case throughout (no `camelCase` and no `snake_case`)

Per-component prefixes already in use. New components MUST pick a
prefix that does not collide with these and stick to BEM:

| Prefix | Owner |
|---|---|
| `top-bar`, `tab-bar`, `tab-content` | shell |
| `dashboard`, `panel`, `stat-card` | dashboard surface |
| `packet-` | packet table |
| `nc-` | node cards |
| `nd-` | node drawer |
| `msg-` | messaging |
| `radio-` | radio settings |
| `ss-` | stats summary |
| `terminal-` | terminal (when it lands) |

---

## File Organization

- One CSS file per major UI surface, under `frontend/css/`.
  Today: `dashboard.css`, `node_cards.css`, `node_drawer.css`,
  `messaging.css`, `radio.css`, `stats.css`.
- Every CSS file is loaded from `<head>` in `frontend/index.html`
  via a separate `<link rel="stylesheet">`.
- Inline `<style>` blocks in `frontend/index.html` are not allowed
  for design-system rules. Per-page micro-tweaks under 10 lines are
  tolerated; anything larger goes in a CSS file.
- Files MUST be saved as UTF-8 without BOM. CSS comments use plain
  ASCII separators (for example `/* ---- Section ---- */`), never
  Unicode box-drawing characters that may be miscoded.

---

## Tech Debt: Legacy Token Drift

Two existing files predate the canonical `:root` block and still use
a legacy fallback namespace:

- `frontend/css/messaging.css` and `frontend/css/radio.css` reference
  `var(--surface-0, #0f0f23)`, `var(--surface-1, #1a1a2e)`,
  `var(--surface-2, #22223a)`, `var(--accent, #4ecdc4)`,
  `var(--border, #2a2a4a)`. These fallback hex values are
  slightly different from the canonical tokens (the legacy teal
  `#4ecdc4` vs canonical cyan `#06b6d4`).
- `frontend/css/node_cards.css` hardcodes a Material-style palette
  (`#00e676`, `#4ecdc4`, `#ffd54f`, `#ff5252`) for signal-quality
  chips.

These files are grandfathered. **Do not extend the legacy
namespace in new code.** All new CSS uses the canonical
`--bg-*` / `--text-*` / `--accent-*` tokens documented above. A
future cleanup PR will refactor the legacy files to the canonical
tokens; that work is intentionally not bundled with regular UI
changes.

---

## Personality

Tokens, BEM, and shell layout get a contributor to "correct."
Personality is what gets a contributor to "this is the kind of
software I want to use." Spend time on it.

The principle: **details that cost almost nothing in code can
make a user feel like the product is exceptional.** Fifty lines
of HTML/CSS/JS, no new dependencies, no new tokens, no shell
changes. Add them on top of working functionality, not in place
of it.

What this looks like in practice:

- **Boot sequences with status checkmarks.** When a panel,
  drawer, or new tab opens for the first time in a session,
  consider a 200ms staged reveal: `Initializing...` → `OK` →
  `Connected` → ready state. Pure visual; no real work happens.
  Sells the impression of a serious system coming online.
- **ASCII or SVG art accents in non-critical surfaces.** A small
  ASCII banner at the top of a logs view, a glyph in a CLI-style
  panel header, a topology micro-rendering in an empty state. Not
  in the primary data view: in the chrome around it. Always
  monospace, always cyan or muted. Never animated to distraction.
- **Status pills that look like industrial gauges.** The auth
  page's identity strip and the wardriving plan's GPS / battery /
  connectivity pills are this pattern. Treat status as a
  first-class visual citizen, not a "(connected)" string.
- **Footer keyboard hints.** When a surface accepts keyboard
  input, list the bindings in a slim 11px monospace footer:
  `↑↓ History · Tab · Esc`. Costs nothing, signals a tool built
  by people who care about keyboard users.
- **Live, low-stakes telemetry rendered in chrome.** A noise
  floor sparkline in a side rail, a packets-per-minute mini
  chart above a table header, a heartbeat dot pulsing in the top
  bar when WebSocket is healthy. The data already exists; the
  cost is one Chart.js call and a 60px slot in the layout.
- **Hero animations that earn their keep.** The auth-radar live
  sweep is this pattern: it does no real work, but it makes the
  login screen feel inhabited. Limit one hero animation per
  surface; never animate the primary data view.
- **Micro-glow on accent elements.** The `--glow-cyan` token
  exists for this; use it on focused inputs, primary buttons in
  hover state, and active-tab indicators. Never on text or on
  surfaces wider than a button.
- **Console-style operator prompts.** `admin@meshpoint:~$` in a
  terminal panel, `RX: 1,247 packets · 0 errors` in a status
  strip, `LongFast · 906.875 MHz · SF11 BW250` in a radio
  header. Speak the language of the operator, not the language
  of the form field.

What this is **not**:

- It is not "make it look like a screenshot from another
  product." Every personality detail in Meshpoint is
  Meshpoint-original, framed as ours, never with a comparative
  citation in code, docs, commits, release blurbs, issues, or
  PRs. The same standing rule that applies to brand voice
  applies here: external products may inform what you ship, but
  no external product is named or credited in any artifact that
  reaches the public repo.
- It is not "add three animations to every screen." One
  intentional detail per surface is the bar. Five is noise.
- It is not "a reason to introduce a new font, palette, or
  shell." Personality lives inside the existing design system.
  If a personality idea requires a new token, the personality
  idea is wrong, not the token list.
- It is not "polish that comes after shipping." Every new
  feature ships with at least one personality detail considered
  during design, not retrofitted later. The auth-radar mockup,
  the wardriving Field Mode tab spec, and the v0.7.3 update
  drawer all designed personality in from the start.

The bar to apply: when adding a new screen, drawer, tab, or
major feature, ask "what's the cheap personality detail here
that costs me 50 lines and makes the user feel like this thing
was built with care?" If the answer is "nothing, it just shows
data," you have not finished the design.

---

## Anti-Patterns (Do Not Do This)

The following patterns will be flagged in PR review and the PR will
be sent back for changes. PR #35 (April 29 2026) is the canonical
example for several of these.

1. **Do not redeclare `:root` design tokens with new names.** Adding
   `--bg-base`, `--amber`, `--teal`, `--text-hi`, etc. fragments the
   palette. Use the existing tokens.
2. **Do not introduce new font families.** `Inter` and
   `JetBrains Mono` are the only families. Loading `Barlow`,
   `Barlow Condensed`, `Share Tech Mono`, etc. is rejected.
3. **Do not put the design system in an inline `<style>` block in
   `index.html`.** The shell layout, color palette, and component
   styles live in `frontend/css/*.css` files.
4. **Do not author CSS in non-UTF-8 encoding.** Save files as UTF-8
   and view the diff in GitHub before pushing. Codepage round-trips
   (most often from terminal-based tools on Windows) can silently
   replace `─` with `ΓöÇ` and `·` with `┬╖`.
5. **Do not change the page `<title>`, top-bar header text, or
   marketing copy** as part of a feature PR. Branding changes go
   in a separate, branding-only PR so they can be reviewed against
   `branding` rules in isolation.
6. **Do not switch naming conventions inside a component.** A
   component is either BEM with double-underscore elements
   (`top-bar__brand`) or it is not. A mix of BEM and bare
   kebab-case (`panel-header`, `nav-item`, `top-stat-val`) inside
   one new component is rejected.
7. **Do not replace the shell layout in a feature PR.** Changing
   `.top-bar` + `.tab-bar` + `.tab-content` to a sidebar shell or a
   different navigation primitive is a design RFC. Open an issue
   first; do not bundle a shell change with feature work.
8. **Do not introduce a new color palette to "match a screenshot"
   from another product.** Meshpoint's identity is the cool
   cyan/green palette over deep navy. Warm amber/teal palettes,
   "hacker green" palettes, light-mode skins, etc. are out of scope.

---

## Review Checklist (PR Author)

Before opening a PR that touches `frontend/`, confirm:

- No new `:root` token redeclarations.
- No new `<link>` to a Google Fonts family beyond Inter and
  JetBrains Mono.
- No inline `<style>` block in `index.html` larger than 10 lines.
- New CSS classes follow BEM with an existing or new component
  prefix listed above.
- All color values are CSS variables, not hardcoded hex.
  Exception: the four signal-quality buckets and the legacy
  `messaging.css` / `radio.css` / `node_cards.css` files are
  grandfathered.
- Page `<title>`, top-bar header, and marketing strings unchanged
  unless this is explicitly a branding PR.
- UI strings honor the brand rules above (`Meshpoint`, no em/en
  dashes).
- New CSS files saved as UTF-8 without BOM, no mojibake in
  comments.
- Shell layout (`.top-bar` + `.tab-bar` + `.tab-content`)
  unchanged unless an RFC issue was opened first.

If you're not sure whether a change conforms, ask in the PR
description rather than guessing. We would rather have the
conversation early.

---

## Related Documents

- `.cursor/rules/branding.mdc` (private repo): brand voice and
  release-blurb style rules. UI strings here must obey the same
  rules.
- `CONTRIBUTING.md`: general PR workflow, branch names, testing
  notes.
