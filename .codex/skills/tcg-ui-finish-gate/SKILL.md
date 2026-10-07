---
name: tcg-ui-finish-gate
description: Apply a final tablet-first UI quality gate to TCG Grader so screens are understandable at a glance, category-driven, touch-friendly, accessible, and free of generic or sprawling layouts.
version: "1.0.0"
---

# TCG UI Finish Gate

Use after implementation and before merge for user-facing tablet changes.

## Product-specific finish gate
1. The first screen must explain the major actions without requiring a long scroll.
2. Prefer category -> feature list -> one detail surface over showing many full panels together.
3. Preserve familiar TCG terms and existing verified actions; do not add decorative complexity that hides status or evidence.
4. Place rarely used diagnostics and legacy tools under an explicit advanced/details area instead of deleting them.
5. Use clear selected, loading, stale, blocked, error, verified, WATCH, and promoted states.
6. Keep touch targets comfortable and focus-visible behavior intact.
7. Prevent layout shift, clipped labels, overlapping sticky controls, and horizontal overflow.
8. Avoid redundant cards, repeated headings, decorative effects, and status badges that do not help a user decide what to do next.

## Review order
- information hierarchy
- category/navigation behavior
- tablet viewport and touch ergonomics
- accessibility/focus/reduced motion
- empty/error/loading states
- performance impact
- screenshot/render validation

## Local-only rule
Do not require design SaaS, hosted browser review, cloud rendering, or cloud AI. Work from repository code and locally rendered output only.
