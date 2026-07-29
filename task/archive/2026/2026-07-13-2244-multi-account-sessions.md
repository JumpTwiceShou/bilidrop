# Multi-account Runtime Sessions

## Scope

- Stop persisting unsaved Cookies between application launches.
- Restore only the last-used saved account profile on startup.
- Allow multiple saved and temporary accounts to run miners concurrently.
- Treat every account as an independent runtime workspace with its own room/task inputs, runtime state, task snapshot, and progress view.
- Let the account-profile selector switch the managed workspace without stopping other accounts.
- Show UID, saved/temporary lifetime, and running state directly in profile labels and a compact account hint.
- Keep temporary accounts in memory only and remove them when the application closes.
- Add focused persistence, session-isolation, GUI-state, packaging, and visual checks.

## Exclusions

- Do not persist temporary Cookies, print account secrets, or use real accounts in tests/screenshots.
- Do not stop the user's currently running legacy packaged process.
- Do not discard the existing uncommitted refactor, stage, commit, push, or publish a public release.

## Ordered Work

- [x] Capture and inspect the current unsaved-account selector state.
- [x] Trace profile persistence and the single-runtime GUI coupling.
- [x] Add saved-profile last-selection metadata without a last-Cookie fallback.
- [x] Add in-memory account session/workspace models and per-account controllers.
- [x] Add temporary-account creation, UID/lifetime/status labels, and saved-profile promotion/deletion.
- [x] Route start/stop/discovery/progress/reward management through the selected account while preserving background accounts.
- [x] Stop all account runtimes safely on application close.
- [x] Add focused tests and update user documentation.
- [x] Capture and compare saved, temporary, and concurrently running account states.
- [x] Build and smoke-test the final single-file executable.
- [x] Audit the scoped diff/security/process state and archive this task.

## Acceptance Criteria

- An unsaved Cookie never appears after restarting the application and the legacy `last-cookie` entry is removed.
- When saved profiles exist, the last selected saved profile is restored on the next launch.
- The selector can hold several saved and temporary accounts at once; temporary entries clearly say that closing the app deletes them.
- Each selector entry shows UID when available and whether that account is running, starting, stopping, idle, or in error.
- Two or more account controllers can run at the same time, including temporary accounts.
- Switching accounts changes the visible Cookie, room/task configuration, runtime badge, task table, and progress details to that account only.
- Starting, stopping, refreshing, discovering, and claiming act only on the currently selected account.
- Closing the main window requests shutdown for every running account.

## Evidence

- Baseline: `main` at `37e137cc5fd780b50dae69a06e2cd67b8da45f18`; prior refactor changes remain intentionally uncommitted.
- User screenshot shows one ambiguous selector entry, `未保存（上次使用）`, even though an unsaved account should not survive restart. It does not communicate UID, lifetime, or per-account running state.
- Product Design saved-context preflight found no stored references; the user's current screenshot and the repository's existing dark UI are the source of truth.
- Full automated suite: 64 tests passed on Windows with fixture-only account data.
- Updated UI capture: `02-multi-account-main.png`; selector states: `03-multi-account-selector-open.png`.
- Combined source/prototype comparison: `05-source-prototype-comparison.png` in the task visualization directory.
- PyInstaller produced one 61,051,640-byte executable. SHA-256: `BF1F482C806F942974A11D59921B3A587439C9E75D406B126515F8995D294B5F`.
- Isolated packaged smoke test created the Qt main window, closed the PyInstaller parent/child process tree through window close messages, and wrote only empty v3 profile metadata with no Cookie values.
- Final `dist/` contains only `bilibili-drops-miner-gui.exe`; the obsolete onedir output was removed after confirming it was not running.

## Decisions

- Keep the existing single-window layout and turn the account selector into a workspace switcher instead of adding a separate account-management page.
- Use one existing `WorkerController` per account session so the proven miner lifecycle remains isolated and reusable.
- Store only the last selected saved credential ID in profile metadata; never persist a temporary Cookie.

## Blockers

- None.

## Commits

- None.

## Device Sync

- Not applicable unless a later explicit commit/push is requested.

## Final Result

- Unsaved Cookies now remain in memory-only temporary workspaces and the legacy `last-cookie` fallback is deleted.
- Saved profiles restore the last selected saved credential without storing secret values in `cookies.json`.
- Saved and temporary accounts own independent controllers, configuration, health, task progress and reward actions, so multiple accounts can run concurrently and remain manageable through the selector.
- Selector labels and the current-account hint expose UID, saved/temporary lifetime and per-account runtime state.
- All account runtimes receive stop requests on window close; the packaged single-file GUI passed isolated startup/close and secret-metadata checks.
