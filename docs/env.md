# Environment - bilidrop

## Current State

No required project-specific env keys were confirmed at Phase 3.

## Infisical

- Project: `dev-secrets`
- Project ID: `cc4ee95f-8c4f-406e-832e-f65cdeb73739`
- Shared path: `/shared/common`
- Project path: `/projects/bilidrop`
- Environment: `dev`
- Local output file: `.env.local`

## Local Files

- `.env.local`: generated local env output, gitignored.
- Account cookies, config files, browser profiles, and generated caches must stay out of Git.

## Rules

- `.env.example` stores variable names only.
- `sync-all-projects` is remote-to-local only and must not upload local changes.
- Adding env keys requires updating `.env.example` and this file, then running `push-project-env` dry-run before explicit apply.
