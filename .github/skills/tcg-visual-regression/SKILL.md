---
name: tcg-visual-regression
description: Prove TCG Grader visual changes with local before-and-after evidence, viewport-matched screenshots, and deterministic layout assertions. Use for UI redesigns, spacing, category panels, mobile/tablet layout, and visible regressions.
version: "1.0.0"
---

# TCG Visual Regression

Use this skill whenever a change is supposed to look different on the tablet.

## Local-only boundary
- Screenshots and comparisons stay on the tablet or a user-owned local machine.
- Do not depend on cloud screenshot services, hosted visual-diff platforms, or external image upload.
- GitHub may store code/PR evidence, but it is not a runtime rendering or learning node.

## Evidence contract
1. Capture or reconstruct the before state before judging the after state.
2. Use the same viewport width, scale, theme, and UI state for before/after comparisons.
3. Check the actual states users touch: home, expanded category, selected feature, long content, and relevant error/empty/loading states.
4. Record structural assertions alongside screenshots so a cosmetic pass cannot hide broken behavior.
5. Flag clipping, overlap, horizontal scrolling, text truncation, tiny touch targets, unexpected long-page expansion, and stale cached UI.

## Tablet priorities
- Category cards are understandable at a glance.
- Long sections stay collapsed until requested.
- Only the selected feature detail is visible when the single-feature contract applies.
- Back/collapse controls remain visible and usable.
- Korean text wrapping remains readable.
- Reduced-motion and dark-mode behavior must not regress.

## Completion
A UI PR is not visually complete merely because CI passes. It needs deterministic UI regression plus rendered local evidence when the environment permits it.
