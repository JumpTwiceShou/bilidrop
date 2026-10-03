# BiliDrop Architecture

## Supported entry points

- Desktop GUI: `python bilibili_gui.py`
- CLI: `python bilibili.py --cookie ... --rooms ...`
- Packaging: `build.py` (PyInstaller, single-file by default) and `build_nuitka.py` (Nuitka)

## Baseline architecture

The pre-refactor runtime created one OS thread and one asyncio event loop for every
room/session pair. Every room's primary session also owned a task poller, while the
GUI ran another task poller. The GUI periodically mutated live miner configuration,
including HTTP client Cookie headers owned by other threads.

Task discovery opened Chrome or Edge with a temporary extension, started at the
Bilibili home page, and waited for the user to visit a live room. It parsed rendered
task groups or intercepted the `totalv2` response. The v2 discovery service now performs
the direct room-data request first and parses both the current nested
`__BILIACT_EVAPAGEDATA__` component tree and the legacy flat `__initialState` structure.
`task_page_fetcher.py` reuses one HTTP session within each discovery, retries a
transient request failure once, and follows activity links from embedded room
configuration or iframes. The HTTP path checks at most three pages and sends at most
six requests, including redirects and retries. The direct-discovery deadline is
checked before requests, between streamed response chunks, and before accepting
parsed task data; network idle waits also have HTTPX timeouts. Only Bilibili URLs
are followed, redirects are validated before requesting
them, and login Cookies are scoped to that domain. If a login Cookie is rejected,
published task pages are retried anonymously without changing the saved account.
Activity data is scoped to the requested room; explicit conflicting room IDs and
recommended-room/advertisement data are excluded, while confirmed short-ID aliases
are retained.
Direct success returns before browser detection or WebDriver startup.
Room live state is checked only after direct task data is absent, so it cannot hide an
offline room's published activity tasks. The fully hidden browser path is a bounded
fallback, the visible flow retains `totalv2` interception, and the GUI exposes
cancellation while discovery is active.

QR login is isolated in `qr_login.py` and `gui_parts/qr_login_dialog.py`. The dialog renders
the QR locally, performs generate/poll requests off the Qt thread, and hands the returned
Cookie to an in-memory account workspace. New Cookies enter the protected credential store
only when the user explicitly promotes that workspace to a saved profile.

`gui_parts/account_sessions.py` models one workspace per saved or temporary account. Every
workspace owns an independent `WorkerController`, task controller, room/task configuration,
runtime health and task snapshot. The selector changes only the workspace rendered by Qt;
other account runtimes continue in the background. Temporary workspaces never enter profile
metadata, while saved metadata records only the most recently selected credential ID.

Each workspace now also owns an explicit run owner, automation state, task phase,
configuration generation and account request coordinator. Background automation may stop
only AUTO-owned runtimes, and results created for an older Cookie/room/task generation are
discarded. Task refresh, automated checks and reward claims for the same account share a
serialized request group and account-level rate-limit cooldown.

Protected profile metadata schema v5 can store optional account-level room and concurrency
settings next to the account remark. Profiles created by older versions have no override and
continue to inherit global defaults. Runtime task IDs, background-auto state and one-time
concurrency overrides are deliberately not persisted.

The account task monitor attempts reward claiming once for every newly completed task and
retries failed claims on later polls. The GUI's manual claim action remains a recovery path.
Advanced settings and the live log viewer are hosted in a modeless secondary window so the
main monitoring surface stays compact while logs continue updating.

Concurrency policy is presented as three distinct layers: 32-session single-account or
16-session-per-account multi-account automatic catch-up / 2-session guarded steady start,
a one-run 100-session override, and a persistent fixed 32-session choice. The one-run
override is cleared when that runtime stops; the persistent choice is written to protected
settings and can be changed later in Advanced Settings.

## Target boundaries

- `domain.py`: application state and data transferred between services and UI.
- `config.py` and `utils.py`: validated configuration and dedicated input parsing.
- `miner.py`: one managed asyncio runtime and bounded room/session tasks.
- `task_monitor.py`: one account-level task poller, notifier and reward coordinator.
- `task_discovery.py`: HTTP-first task discovery with structured outcomes and browser fallbacks.
- `task_page_fetcher.py`: bounded requests to room and linked activity pages.
- `credential_store.py`: protected credential persistence and legacy migration.
- `gui_parts/`: Qt presentation, account workspaces, controllers and explicit run/discovery state.

The GUI and CLI consume the same runtime services. Network services publish typed
snapshots instead of writing widgets directly. Secrets never appear in ordinary
settings, diagnostics, tests or logs.

Room IDs and a Cookie are the runtime prerequisites. Task IDs are optional metadata:
without them, watch-heartbeat sessions still run while task polling, completion
notifications and reward claiming remain inactive.

## Integrity and cancellation

Discovery uses the same schedule selection as automatic mining, including when a
cached page crosses a task boundary. Each GUI discovery owns a cancellation event;
queued callbacks recheck that event and attempt identity before applying results.
Account switches invalidate discovery even while a runtime is already running.
The visible fallback validates room identity and known aliases, opens the target
room directly, and accepts only the first successful capture path.

Progress responses must cover exactly the requested task IDs before they reach
completion or adaptive-concurrency decisions. The account monitor invalidates
cached progress and outstanding claims when tasks change. Claim requests reserve
their generation in event-loop submission order, and caller cancellation propagates
to the batch. Results are associated by task ID; ambiguous checkpoints cannot be
marked claimed by positional inference. Final-claim UI callbacks also verify the
task set and runtime identity before stopping a completed run.

Profile parsing is read-only. Built-in credential stores commit account credentials
and profile metadata as one batch; the Windows store retains DPAPI and performs one
atomic file replacement. Partially loaded profiles cannot replace the original
metadata. Exit-time persistence errors do not skip stopping account runtimes.
