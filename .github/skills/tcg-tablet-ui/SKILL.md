---
name: tcg-tablet-ui
description: 'Design, review, and regression-test the Lenovo/Android tablet UI for TCG Grader, including category navigation, market-lens ordering, responsive layout, readability, and runtime packaging.'
---

# Tablet UI

## UX invariants
- Home shows understandable categories first.
- Detailed content stays hidden until the user selects its category.
- Selecting a category shows only content belonging to that category.
- Home/reset returns to the category-first view.
- Market-driven ordering may reorder existing verified categories; it must not create unverified features.
- WATCH/promoted status should be visible when it materially affects interpretation.

## Responsive rules
- Protect Korean word readability with `word-break: keep-all` where appropriate.
- Avoid narrow multi-column layouts that force one-character-per-line titles.
- Validate tablet-oriented widths as well as phone/desktop fallbacks.
- Keep touch targets usable and avoid layout shifts that hide actions.

## Regression rules
- Derive targets from allowlisted existing IDs/selectors.
- Do not use arbitrary selector/code execution from market data.
- Add deterministic UI regression tests for every navigation/layout behavior change.
- Physical-device verification remains separate from CI/browser validation.
