# AGENTS.md - bilidrop

## Startup

Read `~/.codex/SHARED_AGENT_RULES.md` and the active file under `task/` when the work requires one.

## Scope

This repository tracks the BiliBiliDropsMiner fork and local development around it.

## Canonical Paths

- Current Windows: `D:\dev\repos\bilidrop`.
- Windows VM102: `C:\dev\repos\bilidrop`.
- Ubuntu VM101: `~/src/repos/bilidrop`.
- The old `E:` path is a compatibility junction only.

Direct work on `main` is allowed. Run only checks required by the affected miner workflow and keep account/config data local.

## Remote And Env

- Private development remote: `sync` → `JumpTwiceShou/bilidrop-dev`.
- Public fork/release remote: `origin` → `JumpTwiceShou/bilidrop`.
- External source remote: `upstream` → `mi0e/BiliBiliDropsMiner`; fetch-only unless an upstream contribution is explicitly requested.
- Ordinary development pushes to `sync`; public release requires explicit approval.
- Env paths: `/shared/common` and `/projects/bilidrop`; local output is ignored `.env.local`.
- Never commit env values, tokens, keys, certificates, browser cookies, account configuration, or bootstrap files.

## Commands

- Setup when dependencies are required: `python -m pip install -r requirements.txt`.
- No general test/build command is established; use focused validation only.

## Completion

Check the scoped diff and staged files, state private versus public-release scope, update the task, and archive it when complete.
