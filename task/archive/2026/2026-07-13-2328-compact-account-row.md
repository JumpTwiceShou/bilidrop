# Compact Account Row

## Scope

- Remove the visible “new temporary account” action from the account card.
- Remove the separate account lifetime/status explanation row.
- Put the account selector, remark, save, and delete controls on one compact row.
- Keep Cookie visibility and QR login on the second row.
- Make QR login the account-creation path while preserving existing temporary workspaces.
- Rebuild and validate the single-file Windows executable.

## Exclusions

- Do not change the established dark theme, task/runtime cards, or account persistence rules.
- Do not use real Cookies or account files in tests or screenshots.
- Do not stage, commit, push, or publish a public release.

## Ordered Work

- [x] Inspect the user screenshots and existing account-card implementation.
- [x] Compact the account-card layout and remove redundant controls/copy.
- [x] Route QR login to a new temporary workspace when the current workspace is already occupied.
- [x] Update focused GUI/session tests and documentation.
- [x] Capture the revised account card and complete design QA against the supplied screenshot.
- [x] Run focused validation and rebuild/smoke-test the one-file executable.
- [x] Audit the scoped diff and archive the task.

## Acceptance Criteria

- The account card contains exactly two visible form rows.
- The first row contains selector, remark, save, and delete controls with no “new temporary” button.
- No yellow explanatory row is visible.
- QR login can add another temporary account without overwriting an existing saved, temporary, or running workspace.
- Selector labels continue to communicate UID, lifetime, and runtime state.
- The final executable remains a single file in `dist/`.

## Evidence

- User screenshot `codex-clipboard-9b214585-5bfe-439c-87f3-2818e47fa770.png` shows the selector occupying too much width and actions split across two rows.
- User screenshot `codex-clipboard-873f9ef2-0571-4174-8a51-46c026ad3f1e.png` identifies the redundant yellow explanatory row to remove.
- Product Design saved-context preflight found no saved references; the supplied screenshots and existing dark Qt design system are the source of truth.
- Focused GUI/session validation: 26 tests passed.
- Revised native Qt account-card capture: `02-compact-account-card.png` at 1003 × 147.
- Source/implementation comparison: `04-source-implementation-comparison.png`; `design-qa.md` reports `final result: passed`.
- PyInstaller rebuilt the one-file GUI at 61,051,465 bytes; SHA-256 `E2EB9B1A0F6BFB01E3ADCAF03B27871A860A3A9111CDA3412DC59CEBB8DA8DEB`.
- Isolated packaged smoke test started the PyInstaller parent/child pair, created the Qt window tree, exited both processes through normal close messages, and wrote no Cookie values.
- Scoped diff check is clean, no files are staged, and no repository or smoke-test packaged process remains running.

## Decisions

- Keep compact lifetime/runtime wording inside selector entries instead of a separate hint row.
- Use QR login as the visible account-add action; retain internal workspace creation helpers for behavior and tests.

## Blockers

- None.

## Commits

- None.

## Device Sync

- Not applicable unless a later explicit commit/push is requested.

## Final Result

- The account card now has two visible rows. Selector, remark, save, and delete share the first row; Cookie, reveal, and QR login share the second.
- The visible temporary-account button and yellow explanatory row are removed. The selector entry retains compact UID, lifetime, and runtime state wording.
- QR login remains available while another account runs and creates a new temporary workspace whenever the selected workspace is already occupied, preserving all existing workspaces.
- Focused tests, native visual comparison, design QA, one-file build, and isolated packaged startup/close validation all passed.
