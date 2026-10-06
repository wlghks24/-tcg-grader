---
name: tcg-test-driven-regression
description: Use for any TCG Grader logic change, bug fix, refactor, parser, collector, autonomy, OCR, grading, pricing, or UI behavior change. Prove the change with focused tests before broad regression.
---

# TCG test-driven regression

1. Discover the existing neighboring tests and CI commands before editing code.
2. For a bug, first add or identify a test that reproduces the failure.
3. Make the smallest behavior change that satisfies the intended contract.
4. Run verification in this order:
   - targeted test for the changed behavior;
   - related subsystem regression;
   - current runtime/integration tests affected by the path;
   - repository integrity and relevant SELFREFINE guards;
   - actual output validation when the change produces user-visible or data outputs.
5. Test boundary values explicitly: zero, empty, stale, missing, malformed, duplicated, maximum size, retry/cooldown, and corrupt persisted state.
6. Prefer deterministic tests. Freeze time and isolate filesystem/network state when needed.
7. Do not replace a failing assertion with a weaker assertion unless the requirement itself changed and the PR explains why.
8. For market/price data, tests may verify parsing and gating but must not encode invented current prices as facts.
9. For autonomy, test both allow and hold paths. A recovery path must never bypass an upstream hard blocker.
10. Completion requires the focused test and all directly relevant regressions to be green.
