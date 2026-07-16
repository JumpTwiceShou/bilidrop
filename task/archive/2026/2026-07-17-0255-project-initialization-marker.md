# Add the one-time HomeLab initialization marker

- Status: complete
- Master task: `C:\dev\repos\homelab\task\2026-07-17-0255-project-initialization-gate.md`

## Scope

- Mark this already-initialized managed project with `<!-- homelab-project-initialization: complete -->`.

## Exclusions

- Do not rerun initialization, change product content, touch env values, or include unrelated work.
- Use only the private development remote.

## Ordered Work

- [x] Add exactly one completion marker to the root `AGENTS.md`.
- [x] Validate the scoped diff and marker count.
- [x] Commit and push the scoped metadata change, then archive this task.

## Acceptance Criteria

- The root `AGENTS.md` contains exactly one canonical marker and no project behavior changes.

## Evidence

- The project is present in the HomeLab managed-project manifest and its initialization status was complete before this task.
- The root marker count is exactly one and scoped `git diff --check` passes.

## Decisions

- The marker is durable and does not trigger a repeat initialization.

## Blockers

- None.

## Commits

- `6f6eacc` — `chore: record HomeLab initialization marker` (pushed to private `origin/main`).
- This archive commit records the verified final task result.

## Device Sync

- Tracked by the HomeLab master task.

## Final Result

- Complete. The canonical marker is present exactly once; no product content or unrelated work was included.
