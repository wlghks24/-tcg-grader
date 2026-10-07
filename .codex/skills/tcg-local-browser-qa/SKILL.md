---
name: tcg-local-browser-qa
description: Validate TCG Grader UI behavior with local browser or deterministic local DOM harnesses only. Use for tablet navigation, click flows, visibility, console errors, responsive behavior, and browser regressions without cloud execution.
version: "1.0.0"
---

# TCG Local Browser QA

Use this skill for user-visible HTML/CSS/JavaScript behavior.

## Local-only boundary
1. Run on the tablet or a user-owned local machine only. Do not require Colab, cloud GPUs, hosted browsers, remote browser farms, or paid MCP services.
2. Prefer the existing local server and repository verifiers. A local Chromium/Playwright run is optional when already available; do not make cloud browser access a prerequisite.
3. If real-browser automation is unavailable on Termux, use deterministic DOM/Node regression plus explicit physical-device readback when the user runs it. Never label a simulated DOM test as physical tablet verification.

## Verification flow
1. Identify the exact user flow and viewport.
2. Run the nearest deterministic test first.
3. For category UI, prove initial collapsed state, category expansion, one-feature-at-a-time visibility, back/collapse behavior, and dock routing.
4. Check JavaScript console/runtime errors when a local browser is available.
5. Test at least one narrow/mobile and one tablet-sized viewport for layout changes.
6. Capture failure evidence locally; do not upload screenshots to third-party services automatically.
7. A visible UI change is complete only when code tests and a rendered-output check agree.

## Failure rules
- Hidden content must not remain interactable through accidental overlays.
- A missing target, malformed state, or unsupported browser capability must hold/fail safely.
- Do not weaken selectors, assertions, CSP, service-worker, or runtime guards merely to make a browser test pass.
