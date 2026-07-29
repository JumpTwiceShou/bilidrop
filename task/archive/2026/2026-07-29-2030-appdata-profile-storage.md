# AppData Profiles And Full Daily Tasks

## Scope

- Stop creating or retaining `cookies.json` next to the executable.
- Store account remarks, timestamps, selection state, and DPAPI-protected Cookie values together in `%LOCALAPPDATA%\BiliDrop\credentials.json`.
- Store normal application settings in the same program-owned file and make the main load/save actions use it without a file picker.
- Automatically migrate legacy sibling/CWD `cookies.json` after verified import.
- Move the legacy source into `%LOCALAPPDATA%\BiliDrop\legacy\` so the program directory remains single-file.
- Recognize every task ID in the active current-day task group, not only one task.
- Display every returned task and each meaningful reward checkpoint in the progress table.
- Automatically claim newly completed task/checkpoint rewards while retaining manual claim as a fallback.
- Update focused migration tests, documentation, and the packaged executable.

## Exclusions

- Do not read, print, or expose the user's Cookie values.
- Do not scan unrelated disk locations for credential files.
- Do not stage, commit, push, or publish a release.
- Preserve all unrelated uncommitted refactor work.

## Ordered Work

- [x] Trace current profile/credential paths and migration write order.
- [x] Implement AppData metadata storage and verified legacy migration.
- [x] Move normal settings load/save to the combined store while retaining explicit legacy-file parsing compatibility.
- [x] Cover source and frozen executable paths with focused tests.
- [x] Verify active-day discovery keeps all task IDs.
- [x] Expand task/checkpoint rows and checkpoint-aware automatic claiming.
- [x] Update user documentation and status text.
- [x] Run focused validation and rebuild/smoke-test the single-file executable.
- [x] Audit the scoped diff and archive the task.

## Acceptance Criteria

- New saves create no `cookies.json` beside the executable.
- Profile metadata and DPAPI-protected Cookie values are written together in `%LOCALAPPDATA%\BiliDrop\credentials.json`.
- Saving/loading settings does not open a file dialog and uses the same combined file.
- An old sibling `cookies.json` is loaded, encrypted, represented in the combined credential/profile file, and moved under AppData only after verification succeeds.
- Failed migration preserves the original legacy file.
- The packaged GUI runs without any companion program-data file.
- All task IDs from the active day are monitored together.
- Each meaningful reward checkpoint has its own progress/reward row.
- A newly completed checkpoint triggers automatic claiming without suppressing later checkpoints of the same outer task.

## Evidence

- User explicitly requested that no Cookie/profile file remain next to the program.
- Current `cookie_store_path()` resolves to the executable directory when frozen.
- Current GUI rendering only creates one table row per outer task even though the progress model already contains checkpoints.
- Current automatic claiming permanently marks an outer task after its first successful claim, which can suppress later rewards under that task.
- User confirmed a reached 120-minute checkpoint was not automatically claimed and required the manual fallback.
- `python -m pytest tests/test_credential_store.py -q` passed before integration: 7 tests.
- Final combined focused storage/task/GUI/config validation passed: 69 tests.
- `python -m compileall -q bilibili_drops_miner` passed.
- Single-file GUI rebuilt at `dist/bilibili-drops-miner-gui.exe`: 61,413,102 bytes,
  SHA-256 `1FD5B9AF18E2F0E5C4CCA14A3A2D0EDD339EBC1DB60298270523054954A227ED`.
- Isolated packaged smoke test kept two PyInstaller processes alive for six seconds, created
  no sibling JSON, and left zero related processes after cleanup.

## Decisions

- Use one LocalAppData file for account metadata and protected Cookie values; the Cookie payload remains encrypted.
- Store normal settings as a DPAPI-protected entry inside the same JSON payload; keep account labels and selection indexes as program metadata.
- Preserve one legacy rollback artifact under LocalAppData instead of beside the executable.
- Use the active current-day group as the scope boundary, then keep all of its task IDs.
- Treat each checkpoint as an independently tracked completion marker while using its outer task ID for the existing reward API.

## Blockers

- None.

## Commits

- None.

## Device Sync

- Not applicable unless a later explicit commit/push is requested.

## Final Result

- Completed in the local private working tree without staging, committing, pushing, or
  publishing. The application now uses one protected LocalAppData file for saved settings,
  account metadata, Cookie values, and notification addresses; verified legacy Cookie files
  move out of the executable directory. Active-day discovery retains all task IDs, the GUI
  expands reward checkpoints, and automatic claiming tracks each checkpoint independently.
