# Design QA — Compact Account Card

- Source visual truth: `%USERPROFILE%\AppData\Local\Temp\codex-clipboard-9b214585-5bfe-439c-87f3-2818e47fa770.png`
- Supporting removal target: `%USERPROFILE%\AppData\Local\Temp\codex-clipboard-873f9ef2-0571-4174-8a51-46c026ad3f1e.png`
- Implementation screenshot: `%USERPROFILE%\.codex\visualizations\2026\07\13\019f5a9a-0dd8-72e0-9a32-cc493e50a58f\bilidrop-compact-account\02-compact-account-card.png`
- Full-view comparison: `%USERPROFILE%\.codex\visualizations\2026\07\13\019f5a9a-0dd8-72e0-9a32-cc493e50a58f\bilidrop-compact-account\04-source-implementation-comparison.png`
- Viewport: 1003 px account-card width; desktop dark theme.
- State: empty unsaved temporary account, Cookie masked, no active runtime.

## Findings

- No actionable P0, P1, or P2 differences remain.
- Fonts and typography: the implementation keeps the existing Microsoft YaHei UI/Qt hierarchy, weights, and single-line control text. Labels and button copy remain readable without wrapping or truncation.
- Spacing and layout rhythm: the first row now aligns the selector, remark, save, and delete controls on one center line. The redundant explanatory row is removed, reducing the card from 191 px in the supplied screenshot to 147 px without crowding the Cookie row.
- Colors and visual tokens: existing dark card, neutral inputs, blue save, gray delete/show, and purple QR tokens are unchanged.
- Image quality and asset fidelity: this component contains no raster imagery, illustration, logo, or custom icon asset requiring comparison.
- Copy and content: “新建临时” and the yellow temporary-account sentence are absent. The selector retains the compact `临时·关闭即删` lifetime state requested in the preceding account-profile flow.

## Interaction Evidence

- Focused GUI tests verify that the removed button and hint widget are absent, the four first-row controls share one visual center line, and the selector width is capped at 520 px.
- QR login remains available while the current account is running.
- A QR login for a new Cookie creates a second temporary workspace and preserves the existing temporary account.

## Focused Region Evidence

The account card is itself the complete requested component and all labels and controls are legible at native resolution, so the full-view comparison also serves as the focused-region comparison. No smaller crop is required.

## Comparison History

- Pass 1: the implementation matches the requested two-row structure. The screenshot confirms removal of the extra action and explanation row, a narrower selector, same-row account actions, and unchanged theme tokens. No P0/P1/P2 fix loop was required.

## Implementation Checklist

- [x] Remove visible temporary-account button.
- [x] Remove the yellow explanatory row.
- [x] Place selector, remark, save, and delete on one row.
- [x] Keep Cookie, reveal, and QR login on the second row.
- [x] Preserve multi-account creation through QR login.

## Follow-up Polish

- None required for this targeted revision.

final result: passed
