# Offline Discovery And UI Polish

## Scope

- Make task discovery for an offline room return or cancel promptly instead of holding the UI until the full timeout.
- Keep cancellation responsive throughout direct-data and hidden-browser discovery.
- Add a one-click `守望先锋电竞` preset for room `23612045` and its known task identifier when verified from repository/runtime evidence.
- Remove the unattractive keyboard-focus rectangles from collapsible section headers while preserving keyboard operation.
- Replace numeric spin boxes with plain validated text entry: no plus/minus controls and no mouse-wheel value changes.
- Rebuild and run focused validation for the affected GUI and discovery paths.

## Exclusions

- Do not read, print, or persist the user's real Cookie in task evidence or tests.
- Do not claim rewards, send notifications, commit, push, or publish a public release.
- Do not overwrite or discard the existing uncommitted complete-refactor work.
- Do not fabricate a task ID when Bilibili does not expose one for the requested room.

## Ordered Work

- [x] Capture and audit the reported UI states.
- [x] Reproduce the offline-room timeout and identify the non-cancellable wait path.
- [x] Verify the `守望先锋电竞` room/preset data source.
- [x] Implement prompt offline completion/cancellation and focused regression tests.
- [x] Add the one-click preset and focused GUI tests.
- [x] Remove collapsible-header focus frames and replace spin boxes with plain numeric entry.
- [x] Visually verify the redesigned states.
- [x] Run focused tests, package the GUI, and smoke-test the executable.
- [x] Review scoped diff/security state, record results, and archive the task.

## Acceptance Criteria

- Room `23612045` does not trap the user behind an uncancellable full discovery timeout when offline.
- Clicking cancel interrupts pending discovery quickly and restores usable controls.
- A clearly labeled `守望先锋电竞` action fills/recognizes the configured room and task data in one click.
- Advanced numeric fields accept typed digits only, have no stepper buttons, and ignore mouse-wheel changes.
- Clicking or tabbing through collapsible section headers does not leave the large blue rectangular focus frame shown in the report.
- Existing QR login, running task control, and normal automatic discovery remain intact.

## Evidence

- Baseline: `main` at `37e137cc5fd780b50dae69a06e2cd67b8da45f18`; prior refactor work remains intentionally uncommitted.
- User evidence: offline room `23612045` waits until timeout before cancellation; screenshots show persistent blue focus frames and spin-box stepper gutters.
- Accepted screenshot evidence: `%USERPROFILE%\.codex\visualizations\2026\07\13\019f5a9a-0dd8-72e0-9a32-cc493e50a58f\bilidrop-offline-ui-polish\01-spin-controls-and-focus.png` and `02-collapsed-focus-frames.png`.
- Focused audit: the numeric steppers add visual noise and accidental-scroll risk; the full-width focus frames overwhelm the collapsed headers and make ordinary pointer clicks look like an error/selection state.
- Runtime evidence: Bilibili's room-info response for `23612045` returned code `0`, title `2026守望先锋冠军系列赛  S2季后赛`, and `live_status=0`; the public live page identifies the owner/surface as `守望先锋电竞`.
- Cause: empty offline HTML currently falls through to the hidden-browser loop and its 30-second budget. The main task button is disabled in `DISCOVERING`, so the existing cancellation event has no visible control that can set it.
- The public offline room HTML exposes no current task ID. The preset will therefore set the verified room and start recognition without inventing an ID; any previously saved task IDs remain untouched.
- Focused regression evidence: 24 discovery, browser-action, and GUI-state tests passed, including offline short-circuit, no visible-browser prompt, typed integer validation, ignored wheel input, one-click preset, and cancel-button state.
- Real-room evidence: a 30-second discovery request for offline room `23612045` returned `offline` in 0.65 seconds and did not enter the browser fallback.
- Accepted updated screenshots: `03-updated-advanced-settings.png`, `04-updated-collapsed-headers.png`, and `05-overwatch-cancel-state.png` in the current audit folder. Visual comparison confirms that stepper gutters and bright full-width focus frames are gone while keyboard focus retains a subtle background change.
- Final focused verification: 10 discovery/browser tests, 14 GUI-state tests, and 5 configuration tests passed in isolated Qt-safe runs; `compileall` and `git diff --check` passed.
- Packaging evidence: `python build.py --target gui` completed successfully. The standard executable started hidden, remained responsive, and was stopped after the smoke test without leaving an application or WebDriver process.
- Repository audit: staged files remain empty, generated build/spec outputs remain ignored, and the scoped high-risk secret-value scan found no matches.

## Decisions

- Treat the provided screenshots as the current visual source of truth for this focused polish pass.

## Blockers

- None.

## Commits

- None.

## Device Sync

- Not applicable unless a later explicit commit/push is requested.

## Final Result

- Offline room state is checked before page/browser discovery. Room `23612045` now returns an informative offline result promptly instead of consuming the 30-second browser budget or opening a visible-browser prompt.
- The primary discovery button becomes `取消识别` while discovery is active and sends the existing cancellation signal; repeated cancel clicks are disabled until completion.
- Added a `守望先锋电竞` one-click action that sets verified room `23612045` and starts discovery without replacing or inventing task IDs.
- Replaced all three advanced `QSpinBox` controls with bounded digit-only text fields that expose no steppers and ignore wheel events.
- Removed bright rectangular focus borders from inputs, buttons, checkboxes, and collapsible headers; keyboard focus remains visible through a restrained background/color change.
- Updated user documentation, rebuilt the standard GUI executable, and completed focused runtime/security checks. No commit, push, or public release was performed.
