# Full Daily Task Expansion

## Scope

- Diagnose why the packaged GUI still renders only one task for the active day.
- Inspect the live authenticated task-progress response structurally without printing secrets.
- Expand every current-day task and every reward checkpoint returned by Bilibili.
- Refresh and render task progress immediately after successful recognition, without requiring a manual refresh.
- Keep checkpoint-aware automatic claiming and manual fallback.
- Reflect successful/already-claimed reward results back into the table immediately.
- Prevent manual refresh requests from being lost or leaving the progress view stuck.
- Validate saved-account login state in the background and surface it in the profile selector.
- Block starting an invalid account and direct the user to QR login.
- Merge a QR login into the existing profile with the same UID without overwriting its remark.
- Add focused regression coverage and rebuild the single-file GUI.

## Exclusions

- Do not print, log, copy, or commit Cookie values.
- Do not claim real rewards during diagnosis.
- Do not change unrelated refactor work.
- Do not stage, commit, push, or publish.

## Ordered Work

- [x] Capture redacted live discovery/progress response structure.
- [x] Identify the parser or presentation mismatch.
- [x] Implement complete active-day task/checkpoint expansion.
- [x] Trigger the correct idle/running progress refresh after recognition.
- [x] Update checkpoint rows to `已领取` after automatic or manual claim success.
- [x] Make running refresh signaling race-safe and bound idle refresh duration.
- [x] Add profile login-state validation, display, and start guard.
- [x] Merge same-UID QR login into an existing stopped profile while preserving its remark.
- [x] Add focused tests for the observed response shape.
- [x] Rebuild and smoke-test the single-file GUI.
- [x] Audit the scoped diff and archive this task.

## Acceptance Criteria

- The active day keeps all discovered outer task IDs.
- The task table shows all returned current-day task/reward nodes rather than one summary row.
- Successful recognition immediately populates the progress table.
- Reaching a later node under the same outer task still triggers automatic claiming.
- A successful or already-claimed reward no longer remains labeled `自动领取中`.
- Repeated refresh clicks cannot be lost between polling cycles or permanently cover the task table.
- Saved profiles show checking/valid/invalid login state and invalid accounts cannot start.
- Same-UID QR login refreshes the existing profile Cookie without duplicating it or changing the remark.
- No live reward is claimed during validation.

## Evidence

- User reports the rebuilt program still displays only one task.
- User reports recognized tasks do not appear until clicking manual refresh.
- User confirms the structured rows appear after starting the miner, isolating the one-row problem to the idle refresh path.
- User reports rewards already claimed still display `自动领取中`.
- User reports refresh can remain stuck and only a later click sometimes resumes updates.
- User requests visible login validity, an invalid-login start prompt, and same-UID QR profile merging.
- Redacted live progress probe returned one active-day outer task with five parsed checkpoints.
  At 149/300 minutes, the 60- and 120-minute checkpoints both used status `3`, proving
  that progress completion does not encode whether a reward has been claimed.
- Read-only `mission/info` probing hit Bilibili rate limiting, so it is not polled on every
  refresh. Successful/already-claimed receive results are instead reflected into local
  checkpoint state immediately.
- The idle/manual controller had formatted all checkpoints into one text cell; the running
  monitor already passed a structured snapshot. Both paths now use the structured table.
- Final focused validation passed: 76 tests.
- Read-only login validation checked two saved profiles; both were valid and their returned
  UIDs matched the Cookie UIDs. No nickname or Cookie value was printed.
- The original GUI was still running as two PyInstaller processes and was left untouched.
- Built `dist/bilibili-drops-miner-gui-fixed.exe`: 61,419,873 bytes, SHA-256
  `86D0CD8204528223328DE4074091F19FEE21C39BB46D3F278D634F2B02E3A9F6`.
- Isolated packaged smoke test kept both one-file processes alive, created no sibling JSON,
  and left zero related processes after cleanup.
- The current parser only recognizes a limited set of checkpoint container keys.

## Decisions

- Use a live read-only structural probe with redacted values to avoid guessing the current API schema.

## Blockers

- None.

## Commits

- None.

## Device Sync

- Not applicable unless a later explicit commit/push is requested.

## Final Result

- Completed locally without staging, committing, pushing, publishing, stopping the user's
  active miner, or claiming a real reward. Recognition now immediately renders all five
  current reward checkpoints in separate rows; refresh requests are race-safe; successful
  manual/automatic claims remain displayed as claimed; and saved account login state plus
  same-UID QR refresh behavior are implemented.
