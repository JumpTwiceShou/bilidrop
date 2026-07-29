# BiliDrop UI And Task ID Audit

## Scope

- Review the current desktop UI from the user-provided screenshot and repository implementation.
- Review repository features for concrete reliability, usability, maintainability, and security opportunities.
- Determine whether a room number can drive automatic background task ID extraction.

## Exclusions

- No business-code changes.
- No dependency installation, deployment, push, or public release.
- No account, cookie, or private configuration inspection.

## Ordered Work

- [x] Capture and inspect the supplied screenshot as current-run evidence.
- [x] Map the UI layout and user-visible controls to source code.
- [x] Trace room lookup, task extraction, polling, and thread-safety behavior.
- [x] Review adjacent repository features and identify prioritized opportunities.
- [x] Record evidence, recommendations, validation limits, and final result.

## Acceptance Criteria

- UI recommendations are tied to the supplied screenshot and actual code.
- Task ID automation feasibility is answered with a proposed safe background flow.
- Recommendations are prioritized and distinguish quick wins from structural changes.
- The scoped diff and repository status are checked before completion.

## Evidence

- Repository start state: branch `main`, HEAD `37e137cc5fd780b50dae69a06e2cd67b8da45f18`, clean working tree before this task file.
- Accepted screenshot: `%USERPROFILE%\.codex\visualizations\2026\07\13\019f5a9a-0dd8-72e0-9a32-cc493e50a58f\bilidrop-ui-audit\01-overview.png` (SHA-256 `F0E95E5689DE1DA39903B5C7E72240D1977466CDF18A5F83B9ED1BD21BEA9BC9`).
- UI implementation: `gui_parts/main_layout.py`, `app_style.py`, `styles.py`, and `main_window.py`.
- Task discovery implementation: `browser_actions.py` starts a Selenium sniffer; `browser_sniffer.py` launches Chrome/Edge with a temporary extension; `utils.py` parses `window.__initialState` task groups; the network fallback listens for `/x/task/totalv2`.
- Current public-room check (2026-07-13): `https://live.bilibili.com/23612045` returned HTTP 200 and 74,942 bytes to a plain browser-UA request, but did not include `window.__initialState`; the current static-page parser therefore returned zero task groups without JavaScript execution.
- Runtime dependencies are not installed in this checkout (`httpx` import failed), so no application execution or Selenium-flow capture was attempted.
- Static syntax review parsed all 46 Python files successfully; `git diff --check` passed.
- Parser probes confirmed duplicate room/task IDs are retained and percent-encoded comma-separated task IDs are not URL-decoded.
- No tracked test files exist, and `.gitignore` currently ignores the entire `tests/` directory.

## Decisions

- This is a read-only formal audit; only this task record and audit evidence may be added.
- A plain background HTTP fetch is not a reliable implementation for room-to-task discovery with the current parser; the practical first implementation is an offscreen/headless browser flow with an API/direct-fetch fast path when one is verified.
- The UI audit is scoped to the supplied main-screen state; keyboard focus, screen-reader semantics, error dialogs, resizing behavior, and running-state transitions were inferred from source and not interactively exercised.

## Blockers

- None.

## Commits

- None planned.

## Device Sync

- Not applicable: no product-code change or push requested.

## Final Result

Read-only audit complete.

### UI Findings

1. The configuration card exposes account credentials, room/task discovery, cookie-profile management, advanced concurrency settings, run controls, file actions, and log actions at the same visual level. Reorganize into `账号`, `直播与任务`, and collapsed `高级设置`; keep one primary `开始挂机` action and place load/save/clear near the surface they affect.
2. Replace the repeated `自动获取` buttons with a guided dependency flow: select account, enter room, `识别当前任务`, then start. Show inline states such as `未验证`, `识别中`, `已找到 N 个任务`, and actionable failures.
3. Replace the plain-text task area with structured task rows/cards containing task name, progress, status, reward, and action. Keep raw IDs and logs in a details panel.
4. Use a running-state model to disable fields that cannot safely change live, switch Start/Stop prominence, expose last heartbeat and connected-session counts, and make stopping progress explicit.
5. Protect the Cookie field with masked display and reveal/copy controls. Move saved credentials to OS-backed storage where possible and avoid saving cookies in ordinary config files by default.
6. Accessibility risks: button text contrast is below 4.5:1 for the current green, red, blue, and purple fills; checked checkboxes rely on fill color without a check glyph; no explicit buddies, validators, focus styling, accessible names, tooltips, or tab order were found. Use `QSpinBox` for numeric values and add a visible focus state.
7. The fixed-width horizontal rows and non-wrapping text areas will degrade at the 860px minimum width or increased font scaling. Use a grid/form layout, a vertical splitter for progress/logs, and a scrollable settings container.

### Background Task Discovery

Feasible, with a fallback design:

1. Validate and normalize the room number, then start `TaskDiscoveryController` outside the Qt thread.
2. Fast path: try a verified direct discovery endpoint or cached room result with a short TTL.
3. Rendering path: launch Chrome/Edge with `--headless=new`, navigate directly to `https://live.bilibili.com/{room_id}`, wait for the dynamic task panel, and reuse `extract_bili_live_task_groups`.
4. Automatically choose the active group; if multiple non-active groups remain, return them to the UI for one-time confirmation rather than silently choosing.
5. Fall back to the current visible browser/network sniffer when headless rendering is blocked or times out.
6. Support cancellation, a 20–30 second timeout, structured error reasons, cache invalidation, and automatic re-discovery when task-progress queries report invalid/empty IDs.

The first product increment should add the room-driven headless page-source path without the extension/local HTTP server, retaining the existing visible flow as fallback. A direct API should only become the primary path after its discovery request and account requirements are captured and verified.

### Repository Priorities

1. P0 reliability: replace `thread_count × room_count` OS threads and per-thread event loops with one managed asyncio loop and bounded tasks; apply global concurrency/rate limits and exponential backoff with jitter. The default 128 sessions amplifies resource use and synchronized retries.
2. P0 state safety: cookie/profile changes currently mutate `httpx.AsyncClient` headers from the GUI thread while clients run in other event-loop threads, and account-derived UID/baseline state is retained. Disable account changes while running or perform a controlled miner restart.
3. P0 task ownership: task polling exists both in each room's primary worker and in the GUI timer. Move task polling and completion notifications to one account-level monitor to avoid duplicate requests/notifications and inconsistent state.
4. P0 credential safety: cookies and notification secrets are stored in plaintext JSON. Separate non-secret settings from credentials, use Windows Credential Manager/DPAPI where available, mask secrets in UI/logs, and write local files atomically with restrictive permissions.
5. P1 operational UX: add account/room/task preflight, per-room health, last successful heartbeat, reconnect counts, task-refresh age, notification test, and exportable diagnostic summaries with secrets redacted.
6. P1 input correctness: deduplicate room/task IDs while preserving order, URL-decode pasted `task_ids`, use a dedicated notification-URL parser, validate bounds, and prevent duplicate reward claims.
7. P1 lifecycle: replace daemon-thread shutdown and the nominal force-stop flag with cancellable tasks, bounded graceful shutdown, and a clear final state.
8. P2 engineering: stop ignoring `tests/`, add parser/API fixture/controller concurrency/GUI state tests, and pin or lock runtime dependencies for reproducible releases.

### Scope Statement

- Private development review only; no product code, remote, commit, push, or public-release action was requested or performed.
