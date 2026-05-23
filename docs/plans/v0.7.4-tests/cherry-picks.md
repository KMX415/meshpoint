# Cherry-picks — MQTT hierarchical paths, MeshCore Channel Config, MeshCore map fix

External contributions baked into v0.7.4. Each is verified post-merge.

## 1. MQTT hierarchical topic paths (cherry-pick from PR #35)

**Status:** [ ] Not started  [x] In progress  [ ] Pass  [ ] Blocked  -- cherry-pick landed at `7820f9f`; PR #35 closed with thanks-and-credit comment
**Hardware:** `.141` and `.15`
**Attribution:** `Co-Authored-By: iceice400`

### Functional walkthrough

1. [ ] After cherry-pick lands, verify `tests/test_mqtt_topic_paths.py` passes via `python -m pytest tests/test_mqtt_topic_paths.py -v`.
2. [ ] Configuration > MQTT (lands later in v0.7.4): set topic_root `msh`, region `US`. Live preview shows `msh/US/2/e/<channel>/<gateway>`.
3. [ ] Set topic_root `msh/US/FL`, region (empty or `FL` segment per the new behavior). Live preview shows `msh/US/FL/2/e/<channel>/<gateway>`.
4. [ ] Save. Service restarts (or hot-reloads). Service log shows "MQTT topic prefix resolved: msh/US/FL/2/e/<channel>/<gateway>".
5. [ ] Subscribe to that topic from a separate MQTT client. Verify TX from this Meshpoint publishes to the expected hierarchical path.

### Negative paths

- [ ] Backward compatibility: existing installs with `topic_root: "msh"` and `region: "US"` continue producing `msh/US/2/e/<channel>/<gateway>` (no double region: `msh/US/US/...`).
- [ ] Empty region segment handled gracefully.

### Hardware-specific checks

- [ ] On `.141`, MQTT publishes packets at the expected paths.
- [ ] On `.15`, same.

### Acceptance

- [x] Cherry-pick clean: `git log` shows commit `7820f9f` with `Co-Authored-By: iceice400 <AdamAndrew2468@gmail.com>` trailer (matches the email associated with iceice400's GitHub account, so they will surface as a contributor on the repo front page when feat/v0.7.4 lands on main).
- [x] PR #35 closed with thanks-and-credit comment.
- [ ] CHANGELOG entry mentions iceice400's contribution (lands at version-bump time when Unreleased folds into the v0.7.4 release header).
- [x] `tests/test_mqtt_topic_paths.py` and `tests/test_mqtt_publisher.py` green.

## 2. MeshCore Channel Config (ottoxgam contribution)

**Status:** [ ] Not started  [ ] In progress  [ ] Pass  [ ] Blocked
**Hardware:** `.141` (has MeshCore USB attached)
**Attribution:** ottoxgam, preserved via `--no-ff` merge

### Functional walkthrough

1. [ ] After ottoxgam's branch is rebased onto `feat/v0.7.4` and merged, verify the new endpoints exist.
2. [ ] Configuration > Radio (or wherever the MeshCore section lives in his contribution): MeshCore channel config form visible.
3. [ ] Walkthrough his feature per his PR description (will fill in once PR opens).
4. [ ] Verify existing MeshCore behavior unaffected: contacts list, DM send/receive still work.
5. [ ] `meshpoint setup` still walks the MeshCore configuration step on a fresh install.

### Negative paths

- [ ] Will populate from his PR's test plan.

### Hardware-specific checks

- [ ] On `.141`, MeshCore companion attached via USB; new config applies and persists.
- [ ] If `.15` has MeshCore USB attached, also verify there.

### Acceptance

- [ ] Branch merged with `--no-ff` to preserve attribution.
- [ ] `git log --merges` shows the merge commit; `git log <merge>^2` shows ottoxgam's commits with his author line.
- [ ] CHANGELOG entry credits ottoxgam.

## 3. MeshCore nodes missing from dashboard map (PR #51)

**Status:** [ ] Not started  [x] In progress  [ ] Pass  [ ] Blocked  -- cherry-picked at `8cbd730`; PR #51 closed (CHANGELOG bullet moved from v0.7.3.x to Unreleased so it folds into v0.7.4 at release)
**Hardware:** `.141` (has MeshCore USB)

### Functional walkthrough

1. [ ] After PR #51 rebased onto `feat/v0.7.4` and merged, run pytest to verify regression test passes.
2. [ ] On `.141`, dashboard Node Map should show MeshCore nodes (icons distinct from Meshtastic) wherever GPS coordinates are known.
3. [ ] Click a MeshCore node marker. Expected: popup shows MeshCore-specific fields (pubkey_prefix, contact name).
4. [ ] Compare node count: total nodes in node table should match total markers + nodes-without-coords on the map.

### Negative paths

- [ ] Meshtastic nodes still render correctly (no regression in existing path).
- [ ] Node click does not crash dashboard.

### Hardware-specific checks

- [ ] On `.141`, with active MeshCore companion, at least one MeshCore node renders on the map (assuming any contact has GPS coords).

### Acceptance

- [x] Pre-merge: cherry-picked onto `feat/v0.7.4` at `8cbd730`.
- [x] `tests/test_meshcore_usb.py::TestMeshcoreDecoderNodeExtraction` green (3 cases: advertisement-with-position, advertisement-without-position, standalone POSITION-packet path).
- [ ] Post-merge: visible on `.141` map.
- [ ] CHANGELOG entry credits the PR author (lands at version-bump time).

## Cross-cherry-pick checks

- [ ] All three cherry-picks land on `feat/v0.7.4` before final release tag.
- [ ] Each is independently testable (separate commits for clean attribution).
- [ ] Combined test pass: `python -m pytest tests/ -q` is clean after all three land.
- [ ] Combined ruff: `python -m ruff check src/ tests/` is clean.

## Failure modes to watch

- **Cherry-pick conflicts on MQTT** — likely if Configuration > MQTT lands first. Resolve by accepting the cherry-pick's formatter change and adapting the dashboard preview to reflect it.
- **ottoxgam branch out of date** — he may need to rebase. Maintain a friendly Discord cadence; offer to rebase for him if he asks.
- **PR #51 conflicts with map refactor** — if the sidebar IA refactor changes Node Map markup, the PR may need re-targeting.

## Acceptance summary

- [ ] All three cherry-picks merged onto `feat/v0.7.4`.
- [ ] Functional walkthroughs pass on `.141`.
- [ ] CHANGELOG entries credit each contributor.
- [ ] Sign-off matrix updated.
