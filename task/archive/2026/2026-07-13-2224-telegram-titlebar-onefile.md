# Telegram Notifications, Dark Title Bar And One-file Build

## Scope

- Match the native Windows title bar to the application's existing dark surface.
- Use the supplied `%USERPROFILE%\Downloads\bilibili.png` as the runtime/window icon and packaged executable icon.
- Add native Telegram Bot notifications and make the notification input explain the supported Telegram URL format.
- Include account, monitored room, task, completion state, and automatic reward-claim state in task notifications.
- Produce a single-file Windows GUI executable containing only required runtime dependencies.
- Add focused tests, visual comparison, packaging, and a runtime smoke check.

## Exclusions

- Do not send a real Telegram message or use/read a real Bot token, Chat ID, Cookie, or account secret.
- Do not overwrite or discard the existing uncommitted refactor.
- Do not stage, commit, push, publish a public release, or terminate a user-owned application process.

## Ordered Work

- [x] Capture and inspect the supplied title-bar screenshot and application icon.
- [x] Confirm Telegram Bot API requirements and trace the current notification/reward flow.
- [x] Implement the Windows dark caption and packaged application icon.
- [x] Implement native Telegram Bot delivery and notification input guidance.
- [x] Add account/room/task/completion/claim details to task notifications.
- [x] Add focused regression tests and update documentation.
- [x] Capture and compare the updated window against the supplied screenshot.
- [x] Build and smoke-test the minimal single-file executable.
- [x] Audit the scoped diff/security/process state and archive this task.

## Acceptance Criteria

- Main and secondary windows use a dark Windows title bar consistent with the application background.
- The supplied Bilibili icon appears on the application windows and the packaged executable.
- `tgram://<BotToken>/<ChatID>` is handled without requiring the optional Apprise package.
- The settings input visibly mentions Telegram and its required Bot Token/Chat ID format.
- Completion notifications identify the Bilibili account, monitored room or rooms, task name/ID, completion state, and automatic reward-claim outcome.
- The distributable is one `.exe`, not an exposed dependency directory, and starts successfully on this Windows device.

## Evidence

- Baseline: `main` at `37e137cc5fd780b50dae69a06e2cd67b8da45f18`; existing refactor changes remain intentionally uncommitted.
- Supplied screenshot shows the Windows native caption staying light above the application's dark main surface.
- Supplied icon is a 640×640 Bilibili mark with a transparent/colored background suitable for conversion into multi-size Windows icon resources.
- Product Design saved-context preflight found no prior saved references; the user's current screenshot, icon, and existing repository design system are the source of truth.
- Telegram Bot API confirmation: `sendMessage` is an HTTPS Bot API method requiring `chat_id` and `text`; the lightweight native target posts those fields directly without bundling optional Apprise plugins.
- Windows confirmation: DWM exposes `DWMWA_USE_IMMERSIVE_DARK_MODE`, `DWMWA_CAPTION_COLOR`, `DWMWA_TEXT_COLOR`, and `DWMWA_BORDER_COLOR` for standard native frames. The application now applies the existing `#1a1d23` / `#e6e7eb` palette to every shown top-level Qt window.
- The supplied PNG is copied into `assets/` for Qt runtime use and converted to an ICO build resource; PyInstaller embeds the PNG and applies the ICO to the executable.
- Native Telegram support accepts `tgram://`, `telegram://`, and `tg://` aliases. The settings placeholder and tooltip show the preferred `tgram://BotToken/ChatID` form, and both notification URLs and Bot tokens remain inside the existing protected credential field.
- The account monitor now sends completion/claim status with Bilibili username and UID, all configured room IDs, task name and ID, progress, and reward name. A failed automatic claim produces a retry state and a later successful retry sends a follow-up “reward claimed” update.
- Focused verification: 27 notifier, task-monitor, window-icon, GUI-state, and managed-runtime tests passed; Python bytecode compilation passed. Tests use fixture-only Telegram data and do not send messages or claim real rewards.
- Accepted visual evidence is in `%USERPROFILE%\.codex\visualizations\2026\07\13\019f5a9a-0dd8-72e0-9a32-cc493e50a58f\bilidrop-telegram-onefile`: `02-updated-dark-titlebar.png` shows the full isolated main window, `03-telegram-settings.png` shows the Telegram hint and dark secondary caption, and `04-titlebar-comparison.png` places the supplied light source directly above the matched dark result at the same crop size.
- Visual audit: the white native strip is gone, the supplied Bilibili icon is legible at caption size, native minimize/maximize/close controls remain intact, and the settings field explains Telegram without adding another dense row. Screenshot evidence cannot prove keyboard/screen-reader behavior; the existing accessible input name remains and focused GUI tests cover the live control.
- Packaging: the default GUI build now produces `dist\bilibili-drops-miner-gui.exe`. It excludes Apprise, test/dev UI packages, Pillow, and other unused modules; Selenium lazy imports are limited to the supported Chrome and Edge drivers. The build analysis contains Chrome, Edge, and Selenium Manager while excluding Firefox and Safari.
- Single-file evidence: the final EXE is 61,035,497 bytes with SHA-256 `DC473A8A3779BC4C515BA25FA723631F180002CDED48076CC79B6945A557D481`. A protected, isolated hidden launch observed both PyInstaller parent/child processes alive and responding, then stopped only those smoke-test processes. `05-packaged-exe-icon.png` confirms the supplied icon is embedded in the executable.
- Final audit: `git diff --check` passed, the staging area is empty, generated build/spec/distribution paths are ignored, and no Telegram credentials or user secrets were added. The prior standard directory build was removed after verifying that no process used it. The user-owned `bilibili-drops-miner-gui-next` process and its legacy directory remain untouched because that old version is still running.

## Decisions

- Keep the native Windows frame and apply supported DWM caption attributes instead of replacing it with a fragile custom title bar.
- Keep notification secrets in the existing protected notification-URL storage.

## Blockers

- None.

## Commits

- None.

## Device Sync

- Not applicable unless a later explicit commit/push is requested.

## Final Result

- The application now uses the supplied icon and a native dark Windows caption across top-level windows. Telegram Bot notifications are supported natively with clear protected-input guidance and include account, room, task, progress, reward, and automatic claim state. The default PyInstaller GUI build is a dependency-pruned single EXE; focused tests, visual comparison, module analysis, icon extraction, and an isolated packaged-runtime smoke check all passed.
