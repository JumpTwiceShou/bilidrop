# Settings Window, Cookie Profiles And Rewards

## Scope

- Confirm whether completed task rewards are claimed automatically and make the intended automatic-primary/manual-fallback behavior explicit.
- Explain and correct the state where a protected last-used Cookie is loaded while no named account profile exists.
- Prompt to save a newly added Cookie; use the entered account remark when present, otherwise use its UID as the profile name.
- Remove advanced settings and logs from the main scroll page.
- Add one `设置与日志` button immediately left of the runtime-state badge and open a dedicated secondary window containing advanced settings and live logs.
- Change the default per-room concurrency/session count from 16 to 32 while preserving the valid range.
- Add focused tests, visual verification, packaging, and runtime smoke checks.

## Exclusions

- Do not read, print, or persist the user's real Cookie in task evidence or tests.
- Do not claim real account rewards, send real notifications, commit, push, or publish a release.
- Do not discard or overwrite the existing uncommitted refactor work.

## Ordered Work

- [x] Capture and audit the current account/header/main-page state.
- [x] Trace reward claiming and document the current behavior.
- [x] Trace protected last-Cookie/profile loading and save behavior.
- [x] Implement automatic reward claiming with manual fallback if not already present.
- [x] Implement new-Cookie save confirmation and UID/remark naming rules.
- [x] Move advanced settings and logs into the dedicated secondary window.
- [x] Add the header entry beside the runtime badge and set default concurrency to 32.
- [x] Add focused regression tests and visually verify both windows.
- [x] Package and smoke-test the GUI executable.
- [x] Review scoped diff/security state, record results, and archive the task.

## Acceptance Criteria

- Completed rewards are attempted automatically during normal task monitoring; the manual claim button remains available as a recovery action.
- A Cookie loaded without a selected profile is clearly understood as the protected last-used Cookie, not a hidden profile.
- Adding a new Cookie asks whether to save it as a profile; an entered remark wins, otherwise the UID becomes the name.
- The main page no longer contains expandable advanced settings or runtime logs.
- A single `设置与日志` button is placed left of the runtime-state badge and opens a usable secondary window with both areas.
- Advanced settings continue to load/save and live logs continue updating while the secondary window is open.
- A fresh configuration defaults to 32 sessions per room; existing saved values remain unchanged.

## Evidence

- Baseline: `main` at `37e137cc5fd780b50dae69a06e2cd67b8da45f18`; prior refactor work remains intentionally uncommitted.
- User screenshot shows the main account/runtime surface with no selected profile but a masked Cookie and the runtime badge at the top right.
- Accepted screenshot evidence: `%USERPROFILE%\.codex\visualizations\2026\07\13\019f5a9a-0dd8-72e0-9a32-cc493e50a58f\bilidrop-settings-window\01-current-main-window.png`.
- Focused audit: the main monitoring surface is vertically overloaded by configuration/log sections below the task table; the unused space immediately left of the runtime badge is the clearest entry point for a secondary settings/log surface. The selected-profile empty state and populated Cookie lack explanatory copy, making protected last-Cookie restoration look like an invisible account profile.
- Reward trace: `AccountTaskMonitor.run()` currently polls progress and sends completion notifications but does not call `receive_all_mission_rewards`; claiming occurs only through the manual GUI action. Automatic claiming therefore needs implementation before manual claiming can honestly be described as fallback.
- Cookie trace: `_load_stored_secrets()` restores the independent protected credential key `last-cookie`, while the profile selector is populated only from `cookies.json` metadata. This explains the masked Cookie with `未选择`: it is the last-used protected Cookie, not a hidden profile.
- Existing naming support already extracts `DedeUserID` as `UID <id>` through `default_cookie_remark`; the new prompt can reuse that rule while preserving a user-entered remark.
- Reward implementation: the account monitor now auto-claims newly completed task IDs under the existing claim lock, records successful/already-claimed results, and leaves failures eligible for a later-poll retry. The GUI action is labeled `手动领取` and stays usable as recovery when a completed snapshot is available.
- Cookie implementation: new manual/QR Cookies are stored under the protected `last-cookie` key, then prompt with Chinese `保存` / `暂不保存` actions. A typed remark is preserved; an empty remark uses `UID <DedeUserID>`. Restored unprofiled Cookies display `未保存（上次使用）`.
- Layout implementation: the main page ends after task progress. `设置与日志` sits immediately left of the runtime badge and opens a modeless two-tab window, so settings retain their controls and the existing log timer continues updating the same log widget.
- Focused verification: all 33 account-monitor, GUI-state, config/credential, and QR-login tests passed together; `compileall` and `git diff --check` passed.
- Accepted redesigned evidence: `02-updated-main-window.png`, `03-settings-window-advanced.png`, `04-settings-window-logs.png`, and `05-save-cookie-prompt.png` in the current audit folder. The main window is visibly shorter in information depth, both secondary tabs are complete, and the save prompt clearly exposes the UID-derived name.
- Packaging: the user's existing standard executable remained running and was not interrupted. The completed candidate was therefore built at `dist\bilibili-drops-miner-gui-next\bilibili-drops-miner-gui-next.exe`; a hidden five-second launch confirmed that it stayed alive and responsive, after which only the test process was stopped.
- Final process audit: no candidate process or browser driver remained; only the user's pre-existing standard GUI process remained running. Build, distribution, and generated spec outputs are ignored. Nothing was staged, committed, pushed, or published.

## Decisions

- Use the existing visual system and controls; this is an information-architecture change, not a new theme.

## Blockers

- None.

## Commits

- None.

## Device Sync

- Not applicable unless a later explicit commit/push is requested.

## Final Result

- Automatic reward claiming is now the normal path and manual claiming is the fallback. New Cookies receive an explicit profile-save prompt with remark-first/UID-fallback naming, restored unprofiled credentials are labeled clearly, settings and logs live in a dedicated secondary window, and fresh configurations default to 32 sessions per room. Focused tests, visual review, packaging, and executable smoke validation passed.
