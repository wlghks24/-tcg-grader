---
name: tcg-property-testing
description: Design invariant and property-based tests for TCG Grader grading, calibration, evidence, state machines, parsers, normalization, autonomous decisions, and updater safety.
version: "1.0.0"
---

# TCG Grader Property Testing

Use properties when example tests cannot cover the input domain.

## High-value invariants
- Numeric outputs used for decisions are finite and within their declared bounds.
- Same verified input and same state produce deterministic candidate IDs, splits, rankings, or plans where the implementation promises determinism.
- Normalization/canonicalization is idempotent.
- Duplicate evidence does not increase factual trust.
- Unverified/search/community evidence never becomes official solely through repetition.
- Corrupt or schema-invalid state cannot promote a model/candidate/capability.
- Failed audits cannot enable mutation.
- Disabled mutation flags never execute downstream writes.
- Rollback returns to an already verified owned/champion state, not an invented state.
- Runtime resource protection cannot be overridden by optional learning.

## Tooling
- Use the repository's unittest tests as the mandatory deterministic baseline.
- If Hypothesis is already available for CI/development, add property tests for parsers, normalizers, bounded math, and state transitions.
- Do not make production runtime depend on Hypothesis.
- Persist a minimized regression case as a normal deterministic test after a property test finds a bug.

Avoid properties based on assumptions that are not part of the product contract; encode only documented invariants.
