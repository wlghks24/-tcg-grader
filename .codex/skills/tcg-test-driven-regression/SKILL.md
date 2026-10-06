---
name: tcg-test-driven-regression
description: Prove every TCG Grader behavior change with focused tests first, then related regression and output validation. Use for bugs, logic changes, parser changes, autonomy, OCR, grading, market, or UI behavior.
version: "1.0.0"
---

# TCG Grader Test-Driven Regression

## Change loop
1. Discover the nearest existing tests, fixtures, workflows, and runtime contracts before editing.
2. For a bug, reproduce the original failure with a focused deterministic test before fixing it.
3. Make the smallest behavior change that satisfies the contract.
4. Run verification in order:
   - targeted test,
   - related subsystem regression,
   - current runtime/integration checks for the touched boundary,
   - repository integrity/security/SELFREFINE guards when relevant,
   - actual output validation for user-visible or data-producing changes.
5. Test zero, empty, stale, missing, malformed, duplicate, maximum-size, cooldown/retry, and corrupt-state boundaries when applicable.
6. Freeze time and isolate filesystem/network state where nondeterminism would make the test flaky.
7. Do not weaken assertions or widen a safety threshold merely to make CI pass.
8. Autonomy tests must cover both allow and hold paths; recovery must never bypass an upstream hard blocker.
9. Market/price tests may verify parsing and evidence gates but must not turn invented current values into facts.
10. Completion requires the focused proof and directly related regressions to remain green.
