---
name: tcg-skill-router
description: 'Route any TCG Grader coding, debugging, market-data, tablet-UI, security, or CI task to the smallest compatible repository skill set. Use before substantial repository edits, reviews, bug fixes, autonomous-market changes, or tablet-runtime changes.'
---

# TCG Grader Skill Router

Use the smallest set of repository skills needed for the task.

## Routing
- Code change or PR review -> `tcg-code-review`.
- Test failure, CI failure, regression, rollback, or "fix remaining errors" -> `tcg-regression-recovery`.
- New TCG, prices, releases, promo/events, market evidence, WATCH/promoted -> `tcg-market-evidence`.
- Tablet layout, category navigation, responsive UI, dashboard/readability -> `tcg-tablet-ui`.
- Local rendered browser flow, click/visibility/viewport/console checks -> `tcg-local-browser-qa`.
- Before/after screenshot and layout-diff evidence -> `tcg-visual-regression`.
- Final category-first UI/accessibility/touch finish gate -> `tcg-ui-finish-gate`.
- Missing or weak behavior coverage -> `tcg-test-gap-audit`.
- Recurring defect classes and invalid-state prevention -> `tcg-mistake-proofing`.
- PWA/service-worker/cache/update delivery -> `tcg-pwa-runtime-audit`.
- Agent autonomy, tool use, source discovery, fallback, credentials, external channels -> `tcg-agent-security`.
- Integrity manifest, dependencies, generated evidence, GitHub Actions, provenance -> `tcg-supply-chain`.

For multi-area tasks, combine only the directly relevant skills.

## Repository invariants
1. Preserve fail-closed behavior.
2. Never claim a physical Lenovo/tablet run, readback, network state, or device verification without direct evidence.
3. New TCG discovery may create WATCH candidates; promotion remains evidence-gated.
4. New games never auto-enable grading without separate calibration and regression evidence.
5. Market momentum is a recheck signal, not a profit guarantee or price-direction prediction.
6. Prefer bounded changes and explicit tests over broad self-modifying behavior.
7. Run targeted tests first, then repository-wide regression gates that cover the changed subsystem.
8. Runtime/QA remains local-only: no Colab, cloud training, hosted browser/device farms, cloud rendering, or cloud control plane unless the user explicitly requests a separately reviewed change.
