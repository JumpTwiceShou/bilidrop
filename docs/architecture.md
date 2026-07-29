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

The account task monitor attempts reward claiming once for every newly completed task and
retries failed claims on later polls. The GUI's manual claim action remains a recovery path.
Advanced settings and the live log viewer are hosted in a modeless secondary window so the
main monitoring surface stays compact while logs continue updating.

## Target boundaries

- `domain.py`: application state and data transferred between services and UI.
- `config.py` and `utils.py`: validated configuration and dedicated input parsing.
- `miner.py`: one managed asyncio runtime and bounded room/session tasks.
- `task_monitor.py`: one account-level task poller, notifier and reward coordinator.
- `task_discovery.py`: room-driven headless discovery with structured outcomes.
- `credential_store.py`: protected credential persistence and legacy migration.
- `gui_parts/`: Qt presentation, account workspaces, controllers and explicit run/discovery state.

The GUI and CLI consume the same runtime services. Network services publish typed
snapshots instead of writing widgets directly. Secrets never appear in ordinary
settings, diagnostics, tests or logs.

Room IDs and a Cookie are the runtime prerequisites. Task IDs are optional metadata:
without them, watch-heartbeat sessions still run while task polling, completion
notifications and reward claiming remain inactive.
