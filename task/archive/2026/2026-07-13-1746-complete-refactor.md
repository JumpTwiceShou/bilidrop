# BiliDrop Complete Refactor

## Objective

Completely refactor BiliDrop into a maintainable desktop application whose normal workflow is:

`select account -> enter room -> discover current tasks automatically -> start -> monitor progress/rewards -> stop cleanly`

Users should not need to understand or manually copy task IDs for the normal path.

## Scope

- Refactor runtime concurrency from one OS thread/event loop per session to a managed asyncio runtime with bounded tasks.
- Introduce one account-level task monitor for polling, completion detection, notifications, and reward state.
- Add room-driven automatic task discovery using a headless browser path with the current visible browser sniffer retained as fallback.
- Redesign the PySide6 main window around account, room/task, runtime status, structured task progress, and collapsible advanced/log sections.
- Add explicit application states and prevent unsafe live edits or account switching.
- Separate secrets from ordinary settings, mask credentials in the UI, and provide a credential-storage abstraction with a Windows-protected implementation where practical.
- Normalize and validate room IDs, task IDs, numeric values, and notification URLs.
- Preserve CLI operation and read compatibility for current JSON configuration/cookie profiles, with a safe migration path.
- Add focused automated tests, dependency reproducibility, documentation, and necessary Windows validation.

## Exclusions

- No public release, GitHub Release, deployment, PR, or push without a later explicit user request.
- No use of real account cookies, notification tokens, or private configuration in tests or task evidence.
- No automated reward claiming by default; any new automatic-claim option must be explicit, off by default, rate-limited, and idempotent.
- No unsupported promise that Bilibili private endpoints or anti-abuse behavior will remain stable.
- No unrelated upstream contribution or broad cross-platform browser matrix.

## Compatibility And Safety Decisions

- Baseline rollback point: `37e137cc5fd780b50dae69a06e2cd67b8da45f18` on `main`.
- Preserve existing user files and unrelated work; the archived audit record is pre-existing scoped work and must not be overwritten.
- Legacy plaintext stores may be read for migration, but migration must not delete or rewrite the original until the protected copy is verified.
- Fields that cannot be updated safely while running will be disabled and labeled as requiring restart.
- Network discovery must have cancellation, bounded timeouts, structured errors, and a visible-browser fallback.
- Runtime limits must have conservative defaults, documented maximums, and backoff with jitter.

## Ordered Work

### Phase 0 - Baseline And Test Harness

- [x] Record architecture map, package boundaries, supported entry points, and current behavior fixtures.
- [x] Stop ignoring `tests/`; add a focused test layout and reproducible development-test dependencies.
- [x] Add baseline tests for parsing, task presentation, configuration compatibility, and existing task-group extraction.

### Phase 1 - Domain And Configuration Model

- [x] Introduce typed domain models for account identity, room configuration, discovered task groups, runtime health, and application state.
- [x] Split parsers for room IDs, task IDs, and notification URLs; URL-decode and order-preserving deduplicate applicable inputs.
- [x] Add bounded numeric validation and legacy configuration migration without embedding secrets in new ordinary settings.

### Phase 2 - Managed Runtime

- [x] Replace per-session OS threads/event loops with one owned asyncio runtime and bounded session tasks.
- [x] Add graceful cancellation, deterministic shutdown, connection health reporting, and exponential backoff with jitter.
- [x] Make account changes immutable during a run or perform a controlled stop/reset/restart without cross-thread HTTP-client mutation.

### Phase 3 - Account-Level Task Service

- [x] Move task polling and completion tracking out of room workers into one account-level task monitor.
- [x] Publish structured task snapshots to GUI/CLI consumers and prevent duplicate completion notifications.
- [x] Make reward claiming serialized, idempotent, state-aware, and visibly disabled when nothing is claimable.
- [x] Move blocking notification I/O off the asyncio event loop and add a redacted notification test path.

### Phase 4 - Room-Driven Task Discovery

- [x] Add a cancellable `TaskDiscoveryService` with cache/fast-path hooks and structured outcomes.
- [x] Add a headless Chrome/Edge rendering path that navigates directly to the supplied room and reuses task-group parsing.
- [x] Automatically select the active task group; return ambiguous groups for one-time user confirmation.
- [x] Retain the visible browser/network sniffer as fallback and expose clear timeout/blocked/no-task reasons.
- [x] Trigger re-discovery when stored task IDs are empty, invalid, expired, or no longer return progress.

### Phase 5 - Credential And Settings Storage

- [x] Mask Cookie and notification secrets in the GUI and keep secrets out of logs/diagnostics.
- [x] Add credential-store abstraction and Windows protected storage where runtime support permits.
- [x] Add verified, non-destructive migration from current `cookies.json` and legacy config files.
- [x] Use atomic writes and suitable local permissions for any fallback local store.

### Phase 6 - GUI Information Architecture

- [x] Rebuild the main window into account, room/task, runtime status, task progress, advanced settings, and log surfaces.
- [x] Replace repeated `自动获取` actions with the guided room-to-task workflow and inline discovery states.
- [x] Replace plain-text task progress with structured rows/cards showing progress, status, reward, and action.
- [x] Add a clear run-state machine that changes Start/Stop prominence and locks unsafe fields.
- [x] Use numeric controls, responsive/grid layouts, splitters/scroll areas, visible keyboard focus, accessible labels, check glyphs, and compliant text contrast.
- [x] Keep advanced settings and logs collapsible; move actions next to the content they affect.

### Phase 7 - CLI And Diagnostics

- [x] Preserve existing CLI arguments while routing them through the refactored domain/runtime services.
- [x] Add useful redacted diagnostics: account validity state, room health, connection counts, last heartbeat, reconnect count, task refresh age, and last structured error.
- [x] Ensure diagnostic export cannot include cookies, tokens, browser data, or notification credentials.

### Phase 8 - Focused Verification And Documentation

- [x] Run parser/config/task-monitor/runtime-shutdown/task-discovery unit tests with fixtures and mocks.
- [x] Run PySide6 offscreen smoke tests for initial, discovering, running, stopping, error, and empty-task states.
- [x] Run focused Windows browser discovery validation without private credentials; document unverified account-only behavior.
- [x] Run syntax/import/CLI-help checks and the affected packaging smoke check.
- [x] Update README, example config, migration notes, architecture notes, and troubleshooting.
- [x] Inspect the scoped diff, staged files, ignored files, and secret exposure before completion.

## Acceptance Criteria

### User Workflow

- A user can select or enter an account, enter a room number, discover the current task group in the background, start, observe structured progress, claim eligible rewards manually, and stop without handling raw task IDs.
- When background discovery cannot succeed, the UI explains why and offers the existing visible-browser fallback.
- Multiple task groups are never silently resolved incorrectly; the active group is automatic and ambiguous choices are confirmed.

### Runtime And Correctness

- Session count no longer maps one-to-one to OS threads or independent event loops.
- One account has one task polling/notification owner regardless of room count.
- Stop completes through cancellation and bounded joins without relying on daemon-thread process exit.
- Account changes cannot leave old UID, watch baseline, task notification, HTTP header, or room state attached to the new account.
- Duplicate and encoded room/task inputs are normalized correctly; invalid numeric values cannot enter runtime configuration.

### Security

- New ordinary settings do not contain cookies or notification secrets.
- Credential fields are masked by default and all logs, diagnostics, task files, tests, and screenshots remain secret-free.
- Legacy migration is verified before any user-owned plaintext source is changed or removed.

### GUI And Accessibility

- The primary workflow is visually dominant and advanced settings no longer compete with it.
- Task state is structured rather than presented only as monospaced text.
- Keyboard focus is visible, labels are programmatically associated, controls have appropriate names, checked state is not color-only, and normal-size text meets the chosen contrast target.
- The main window remains usable at its supported minimum size and increased Windows text scaling.

### Compatibility And Evidence

- Existing CLI usage and legacy readable config/profile formats have covered compatibility tests or documented migrations.
- Focused automated checks cover parsers, configuration, task monitoring, runtime lifecycle, discovery decisions, and main GUI states.
- Any behavior requiring a real Bilibili account is explicitly marked unverified unless the user later authorizes local credential-based testing.

## Evidence

- Start state: `main` at `37e137cc5fd780b50dae69a06e2cd67b8da45f18`.
- Start worktree: clean product tree plus untracked archived audit record `task/archive/2026/2026-07-13-1733-ui-and-task-id-audit.md` from the immediately preceding read-only audit.
- Audit basis: `task/archive/2026/2026-07-13-1733-ui-and-task-id-audit.md`.
- 2026-07-13 Phase 0/1: added `docs/architecture.md`, typed domain models, dedicated normalized parsers, bounded configuration defaults, atomic settings writes, pinned runtime/dev dependencies, and 10 baseline tests. `python -m pytest` passed (`10 passed`).
- 2026-07-13 Phase 2/3: moved all sessions to one asyncio runtime, added deterministic cancellation/health callbacks/jitter, and introduced one account-level task monitor with serialized rewards and off-loop notifications. Managed-runtime and task-monitor tests raised the suite to 14 passing tests.
- 2026-07-13 Phase 4: added cached/cancellable room-driven headless discovery, active-group selection, ambiguity handling, visible-browser fallback, and one-shot runtime re-discovery. Discovery tests raised the suite to 17 passing tests.
- 2026-07-13 Phase 5/6/7: added DPAPI-backed credential storage with verified legacy backup/migration, secret-free settings/diagnostics, guided and scrollable Qt layout, structured task table, explicit application states, protected fields, notification test, and CLI compatibility. Credential and GUI-state tests raised the suite to 23 passing tests.
- Accepted offscreen layout capture (font-independent geometry check): `%USERPROFILE%\.codex\visualizations\2026\07\13\019f5a9a-0dd8-72e0-9a32-cc493e50a58f\bilidrop-complete-refactor\01-refactored-main.png`.
- 2026-07-13 focused verification: `python -m pytest` passed (`32 passed`), including all six application states and the empty-task surface; compileall, CLI help, and `git diff --check` passed.
- 2026-07-13 native Windows layout capture rendered Chinese and the full primary workflow correctly: `%USERPROFILE%\.codex\visualizations\2026\07\13\019f5a9a-0dd8-72e0-9a32-cc493e50a58f\bilidrop-complete-refactor\03-windows-native-main.png`.
- 2026-07-13 headless discovery smoke test launched the installed browser against public room `23612045`, returned a bounded timeout/no-task outcome, and left no Chrome/Edge/WebDriver process behind. Account-only task discovery, notification delivery, and reward claiming remain intentionally unverified without user credentials.
- 2026-07-13 final native Windows capture verified readable Chinese, primary visual hierarchy, structured task table, and visually distinct disabled actions: `%USERPROFILE%\.codex\visualizations\2026\07\13\019f5a9a-0dd8-72e0-9a32-cc493e50a58f\bilidrop-complete-refactor\04-windows-native-final.png`.
- 2026-07-13 PyInstaller `6.20.0` GUI development build completed successfully at ignored path `dist/bilibili-drops-miner-gui/`; the packaged EXE started and remained responsive during a bounded smoke test, then the test process was removed.
- 2026-07-13 final repository audit: `git diff --check` passed, the index was empty, tests were not ignored, build/dist/spec outputs were ignored, and the changed/new-file secret marker scan returned no matches.

## Decisions

- The refactor will be implemented in verifiable vertical phases; unchecked items are not considered complete.
- Compatibility shims may remain temporarily, but new GUI and runtime code must not depend on unsafe cross-thread mutation.
- Prefer a simpler service boundary and explicit state transitions over preserving current internal module layout.

## Blockers

- None at task creation.

## Commits

- None yet.

## Device Sync

- Not applicable: no commit or push was requested or performed. Public-release scope remains excluded.

## Final Result

- Complete. The v2 refactor now provides a guided room-to-task GUI, background room-driven discovery with safe fallback, a single managed asyncio runtime, one account-level task monitor, protected local credentials, redacted diagnostics, CLI compatibility, reproducible dependencies, focused documentation, and 32 passing automated tests.
- Private development scope only. No real account credential, notification delivery, reward claim, commit, push, PR, deployment, or public release was performed.
