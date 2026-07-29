# Optional Task Discovery

## Scope

- Diagnose the general task-discovery regression using room `23612045` as runtime evidence, without adding room-specific logic.
- Restore the invariant that a valid Cookie and room number are sufficient to start watch-time mining.
- Make task IDs optional for runtime startup; limit their absence to task progress, notifications, and reward claiming.
- Support both Bilibili's legacy flat task state and its current nested EVA activity-component state for every task room.
- Update focused tests, user-facing status copy, documentation, and the single-file executable.
- Preserve packaged-app loading and non-destructive migration of legacy sibling `cookies.json` profiles.

## Exclusions

- Do not read, print, or persist the user's real Cookie.
- Do not require a live campaign or real account for automated validation.
- Do not stage, commit, push, or publish a public release.
- Preserve all unrelated uncommitted refactor work.

## Ordered Work

- [x] Trace GUI startup gating, config validation, task monitor construction, and discovery fallbacks.
- [x] Reproduce the current-page parsing failure with Chrome and identify the changed Bilibili activity-state schema.
- [x] Allow runtime startup with room IDs and no task IDs.
- [x] Parse current and legacy task activity structures before using browser automation as a bounded fallback.
- [x] Add focused tests and update user documentation/status messaging.
- [x] Run necessary validation and rebuild/smoke-test the single-file executable.
- [x] Audit the scoped diff, record private/public scope, and archive the task.

## Acceptance Criteria

- Clicking “开始挂机” with a valid Cookie and room number starts immediately even when task IDs are empty.
- Empty task IDs do not prevent watch-heartbeat sessions, do not claim rewards, and show a clear non-blocking status.
- Task discovery does not use live/offline state as a prerequisite for reading activity task data.
- Any room using Bilibili's current nested EVA activity state can be recognized without a room-specific preset or hard-coded task ID.
- An offline room result no longer prevents the miner runtime from starting.
- Focused tests cover optional task IDs and offline direct discovery.
- A packaged path resolves and loads the legacy `cookies.json` next to the executable.

## Evidence

- User reports both background and browser discovery fail for Overwatch Esports room `23612045`.
- Current GUI behavior requires successful task discovery before startup even though watch heartbeat only needs account and room configuration.
- Chrome runtime inspection on 2026-07-29 confirmed room `23612045` currently exposes task groups under `window.__BILIACT_EVAPAGEDATA__`; the old parser only reads flat keys under `window.__initialState`.
- The inspected page did not issue `/x/task/totalv2` during initial navigation, so network capture is a fallback/progress path rather than a reliable source for discovering unknown task IDs.
- Chrome inspection showed the current room page contains five dated `EvaTabs.Panel` task groups, with one active group and `EraTasklistPc.props.tasklist[].taskId` values.
- A no-Cookie direct discovery check against the current public room returned `success`, source `direct`, five groups, one active group, and one selected task without starting a browser.
- The visible-browser `/x/task/totalv2` callback remains wired and has a regression test that extracts multiple task IDs from a captured response.
- Focused discovery/parser/browser/GUI validation passed 42 tests. Adjacent runtime/config validation passed 15 tests, legacy credential validation passed 6 tests, and compileall plus `git diff --check` passed.
- The packaged-path test confirms a frozen executable loads old list/object-format `cookies.json` from its own directory. Migration uses a synthetic fixture only and does not inspect the user's file.
- `python build.py --target gui --clean` produced `dist\bilibili-drops-miner-gui.exe` (61,401,860 bytes, SHA-256 `3B9450048353F1C6B2E5FC96DBE1F58A81EC5D5754D099C88CF27E7F4872B765`).
- An isolated offscreen smoke launch kept the one-file executable running with two PyInstaller processes and created neither a Cookie file nor a credential file.
- A forced real hidden-browser fallback on 2026-07-29 disabled direct HTML discovery and used headless Chrome against room `23612045`; it returned `success` in 4.82 seconds with five groups, one active group and one selected task. No new ChromeDriver or EdgeDriver process remained afterward.
- The existing `dist\cookies.json` remained untouched at 270 bytes with its original 2026-07-29 20:08:52 modification time.
- Repository is on `main` at `ebf9c1e8efbc84b60eb73b0e6099b60e375010d5`; existing uncommitted refactor changes are preserved.

## Decisions

- Treat task discovery as an enhancement for monitoring/rewards, not a prerequisite for watch-time mining.
- Parse public/authenticated page activity state first; use hidden or visible browser automation only as bounded fallbacks.
- Keep the existing Overwatch button as a room-entry convenience only; do not hard-code room-specific task IDs or discovery behavior.
- Treat task IDs as optional runtime metadata. Empty IDs keep the account monitor idle and therefore cannot query progress or claim rewards.
- Legacy sibling `cookies.json` remains the explicit upgrade boundary; the application will not scan unrelated disk locations for credentials.

## Blockers

- None.

## Commits

- None.

## Device Sync

- Not applicable unless a later explicit commit/push is requested.

## Final Result

- Restored general discovery for Bilibili's current nested EVA activity pages while retaining legacy initial-state and `totalv2` compatibility.
- Removed task discovery as a startup prerequisite: a valid Cookie and room now start watch-heartbeat sessions immediately even when task IDs are empty.
- Moved live/offline checking after direct task-data parsing so published tasks are not hidden by room state; a genuinely offline room with no task data still returns promptly.
- Verified packaged legacy-Cookie loading, rebuilt the single-file GUI, and completed an isolated smoke launch.
- Work remains private and local. No files were staged, committed, pushed, or published.
