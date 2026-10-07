---
name: tcg-tablet-ui-ux
description: Review and evolve the TCG Grader tablet interface for Android readability, category focus, touch ergonomics, responsive layout, low-resource rendering, and evidence-honest states.
version: "1.0.0"
---

# TCG Grader Tablet UI / UX

Use this skill for the 1600×2560 tablet surface, feature categories, navigation, market/game selectors, grading capture, collection/portfolio panels, and status dashboards.

## Tablet-first rules
1. Validate the real target viewport before changing layout; desktop appearance is not sufficient.
2. Keep Korean labels readable with bounded wrapping and touch targets large enough for tablet use.
3. Preserve category focus: home shows categories, selecting one reveals only its relevant features, and Home returns predictably.
4. Registry-driven games must show state honestly: core/promoted/watch/reverify are visually distinct; WATCH must not look fully supported.
5. Loading, missing, stale, provisional, verified, blocked, rate-limited, and error states need distinct user-visible treatment.
6. Do not render repeated placeholder cards that create long empty scrolling; use bounded summaries and progressive disclosure.
7. Expensive images/charts/network panels load only when needed. Respect reduced motion and low-resource operation.
8. Navigation targets remain allowlisted DOM targets; adaptive layout may reorder existing features but cannot invent selectors/URLs/actions.
9. A new market category may reuse market/release/promo/purchase surfaces automatically after registry verification, while grading stays hidden/disabled until calibration.
10. Review with screenshot/video evidence when available, then add deterministic DOM/CSS regression assertions for the defect.

## Completion
UI work is complete only after syntax tests, category/navigation regression, responsive checks, tablet runtime packaging, and representative screen/output validation pass.
