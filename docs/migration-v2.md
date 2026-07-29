# Migrating To BiliDrop v2

## What remains compatible

- Existing GUI JSON settings can still be loaded.
- Existing `cookies.json` list/object formats can still be read.
- Existing CLI argument names remain available.
- Existing task ID strings and `totalv2?task_ids=...` URLs remain accepted.
- Browser login is no longer the primary GUI flow. Use the in-app QR dialog; existing
  manually entered or migrated Cookies remain supported.
- Task discovery reads room activity data before considering live/offline state. It
  supports both the current nested EVA component tree and the old flat initial state,
  then uses a hidden browser only when necessary. The visible fallback still intercepts
  `/x/task/totalv2`.
- The GUI includes a one-click Overwatch Esports preset for room `23612045`.
- Advanced numeric settings are plain validated text fields and ignore mouse-wheel input.
- Advanced settings and runtime logs now open from a dedicated header action instead of
  occupying expandable sections in the main page.
- Every task ID in the active current-day group is monitored together. Checkpoint rewards
  such as 60/120/180/240-minute milestones are displayed and automatically claimed
  independently; manual claiming remains available for recovery.
- Recognition immediately requests a structured progress snapshot. The idle/manual path and
  the running monitor now feed the same multi-row table instead of collapsing idle results
  into one text cell.
- Saved profiles are validated through the account navigation API. Invalid profiles are
  blocked from starting, and a same-UID QR login refreshes the existing stopped profile
  without changing its remark.

## Runtime changes

`thread_count` is retained as the compatibility field name, but it now means
asynchronous sessions per room. It no longer creates that many OS threads. The new
default is 16 and the accepted range is 1–128.

Task polling is account-level. Adding rooms no longer creates additional task
pollers or duplicate completion notifications.

Task IDs are no longer a startup requirement. A Cookie and at least one room ID can
start watch-heartbeat sessions immediately; missing task IDs only disable progress
queries, completion notifications and reward claiming until tasks are identified.

Runtime configuration is immutable. Stop before changing account, room, session
count, reconnect delay, notification address or task interval for that account. The
profile selector remains available so another saved or temporary account can be configured
and started while existing account runtimes continue in the background. Automatically
re-discovered task IDs are the only live-updated task setting.

## Credential migration

On Windows, account metadata, DPAPI-protected secrets, and saved application settings are
stored together under `%LOCALAPPDATA%\BiliDrop\credentials.json`. The settings load/save
buttons use this file directly and no longer open a file picker.

The old protected `last-cookie` fallback is removed during startup. Unsaved Cookies are now
temporary in-memory workspaces and disappear when the program closes. Newly added Cookies
still prompt for profile creation and default to the Bilibili UID when no remark is supplied.
Profile metadata stores the last selected saved credential ID, so only a saved profile can
be restored on the next launch.

When a legacy cookie profile is loaded, its Cookie and profile metadata are copied to the
combined store and read back for verification. Only after verification succeeds is the
legacy source moved to `%LOCALAPPDATA%\BiliDrop\legacy\`. A failed write or verification
leaves the original file in place, and no `cookies.json` remains next to the executable
after a successful migration.

Legacy JSON settings containing `cookie` or `notify_urls` remain readable. When loaded in
the GUI, a Cookie creates a temporary account rather than being persisted automatically;
notification URLs still move to protected storage. Saving settings creates a secret-free file.

## Rollback

Before a public release, keep the v1 executable and the migrated backup under the
LocalAppData `legacy` directory. v1 cannot read the combined credential metadata, so
rollback requires restoring that backup manually. Never commit either file.

## Behavior requiring manual validation

- Real account login and x25Kn heartbeat acceptance.
- Real task discovery for currently active campaigns.
- Notification delivery for user-owned endpoints.
- Reward availability and claiming.

Automated tests use fixtures and fakes only; they do not read local account files.
