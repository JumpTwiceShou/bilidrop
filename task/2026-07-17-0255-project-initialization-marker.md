# Add the one-time HomeLab initialization marker

- Status: active
- Master task: `C:\dev\repos\homelab\task\2026-07-17-0255-project-initialization-gate.md`

## Scope

- Mark this already-initialized managed project with `<!-- homelab-project-initialization: complete -->`.

## Exclusions

- Do not rerun initialization, change product content, touch env values, or include unrelated work.
- Use only the private development remote.

## Ordered Work

- [x] Add exactly one completion marker to the root `AGENTS.md`.
- [x] Validate the scoped diff and marker count.
- [ ] Commit and push the scoped metadata change, then archive this task.

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

- Pending.

## Device Sync

- Tracked by the HomeLab master task.

## Final Result

- Pending.
