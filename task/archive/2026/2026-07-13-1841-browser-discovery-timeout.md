# UI, Background Discovery And QR Login Completion

## Scope

- Diagnose the reported Edge renderer timeout during background room-to-task discovery.
- Make discovery reuse the browser selected by the user where possible.
- Provide the authenticated Cookie to the isolated headless browser without logging it.
- Bound each browser attempt, fall back to the next installed browser, and replace raw WebDriver stack traces with concise Chinese status messages.
- Add focused regression tests and update user-facing troubleshooting if behavior changes.
- Redesign the expanded advanced-settings surface into clear grouped controls with consistent spacing and action hierarchy.
- Ensure all automatic discovery is genuinely background-only on Windows, including hiding WebDriver service processes.
- Discover task IDs without depending on the room being live; prefer an authenticated direct-data path and keep browser rendering only as fallback.
- Replace browser-based login as the primary flow with Bilibili QR-code API login, using `C:\dev\repos\bilibilistream\plugin1\obs-bilibili-stream-master` as the requested local implementation reference.

## Exclusions

- Do not read, print, store in task evidence, or test with the user's real Cookie.
- Do not send notifications, claim rewards, publish releases, commit, or push.
- Do not overwrite the existing complete-refactor worktree changes.
- Do not copy secrets, generated files, or unrelated code from the reference repository.

## Ordered Work

- [x] Confirm the failure path and record the implementation cause.
- [x] Implement authenticated, bounded, preferred-browser discovery with automatic fallback.
- [x] Inspect the requested local QR-login/API reference and identify reusable protocol behavior.
- [x] Add an authenticated direct-data-first task discovery path that does not require a live-status check.
- [x] Add API QR-code login with an in-app QR dialog and protected Cookie handoff.
- [x] Redesign and visually verify the expanded advanced-settings UI.
- [x] Hide browser/driver subprocess windows on Windows and retain headless DOM discovery only as fallback.
- [x] Add regression tests for Cookie injection, direct-data discovery, timeout summarization, browser fallback, QR login, and GUI wiring.
- [x] Run focused tests and syntax/diff/security checks.
- [x] Record the result and archive the task.

## Acceptance Criteria

- A Chrome selection made during Cookie/room acquisition is reused for background task discovery before Edge.
- The headless discovery browser receives the current Bilibili Cookie in memory before visiting the live room; it is never logged.
- One renderer timeout does not consume the whole discovery window or prevent trying the next available browser.
- Logs and dialogs contain a short browser-specific explanation, not a WebDriver stack trace.
- Browser drivers started by the discovery path are always closed.
- Offline rooms use the same authenticated direct-data discovery path; the application does not reject discovery based on live status.
- Clicking login shows a QR code inside the application, polls bounded status, and stores the returned Cookie without opening a browser.
- The advanced section uses understandable groups and balanced layout at the supported window width.
- No browser or WebDriver console/blank window appears during background fallback discovery on Windows.

## Evidence

- Baseline: `main` at `37e137cc5fd780b50dae69a06e2cd67b8da45f18`, with the prior complete-refactor changes still intentionally uncommitted.
- User runtime evidence: Cookie and room extraction through visible Chrome succeeded; background task discovery selected Edge and emitted `Timed out receiving message from renderer` plus a full WebDriver stack trace.
- Code inspection: `BrowserActions.auto_fetch_task_ids()` did not pass the previously selected browser or current Cookie. `TaskDiscoveryService` used one shared deadline across all browsers and logged `str(WebDriverException)`, which contains the stack trace.
- Local reference evidence: `bilibili_api.cpp` uses the official QR generate/poll endpoints and handles status codes `86101`, `86090`, `86038`, and success; `dialog_factory.cpp` renders the QR inside Qt and polls off the UI path. The Python implementation follows this protocol without copying unrelated C++ code.
- Focused verification after QR/API/UI implementation: 21 tests passed across QR login, direct/offline discovery, browser fallback, browser/Cookie reuse, and GUI states; compileall and `git diff --check` passed.
- Accepted current UI evidence: `%USERPROFILE%\.codex\visualizations\2026\07\13\019f5a9a-0dd8-72e0-9a32-cc493e50a58f\bilidrop-settings-audit\01-current-advanced-settings.png`.
- Accepted redesigned expanded-settings evidence: `%USERPROFILE%\.codex\visualizations\2026\07\13\019f5a9a-0dd8-72e0-9a32-cc493e50a58f\bilidrop-settings-audit\03-redesigned-advanced-settings-bottom.png`.
- Accepted in-app QR-login dialog evidence (fixture QR only): `%USERPROFILE%\.codex\visualizations\2026\07\13\019f5a9a-0dd8-72e0-9a32-cc493e50a58f\bilidrop-settings-audit\04-qr-login-dialog.png`.
- Official QR endpoint smoke evidence: a fresh session was created and its first poll returned `pending`; neither the QR URL nor key was printed or persisted.
- Windows hidden-browser evidence: during a 12-second Chrome-first discovery run, all newly created Chrome and ChromeDriver processes reported `MainWindowHandle=0`; fallback ended with concise timeout summaries, all new Chrome/driver processes exited, and no WebDriver stack trace was emitted.
- Final regression evidence: `python -m pytest -q` completed with 41 tests passing; `compileall` and `git diff --check` passed.
- Packaging evidence: the standard GUI bundle completed at `dist\bilibili-drops-miner-gui\bilibili-drops-miner-gui.exe`; a hidden smoke launch was running, responsive, and had no visible top-level window before the test process was stopped.
- Repository audit: the staged set is empty, build/spec outputs remain ignored, the scoped high-risk secret-value scan found no matches, and no ChromeDriver or EdgeDriver process remained after validation.

## Decisions

- Keep headless discovery as the normal path and the visible sniffer as the user-confirmed fallback.
- Inject only parsed Bilibili Cookie pairs into the temporary browser session and discard the session after every attempt.

## Blockers

- None.

## Commits

- None.

## Device Sync

- Not applicable unless a later explicit commit/push is requested.

## Final Result

- Replaced the primary browser login with an in-app Bilibili QR API flow that hands the returned Cookie directly to protected local storage.
- Reworked task discovery to try authenticated room data before a bounded hidden-browser fallback, without rejecting offline rooms based on live status.
- Reused the selected browser and in-memory Cookie for fallback discovery, hid Windows driver/browser subprocesses, and reduced renderer failures to concise Chinese status messages.
- Redesigned the advanced-settings area into balanced functional groups with visible checkboxes and a clear action hierarchy.
- Completed regression, packaging, runtime, diff, and sensitive-value checks. No commit, push, or public release was performed.
- A real scanned-login completion and authenticated offline-room response still require the user's account/device for end-to-end confirmation; no unsupported success is claimed for those two external states.
