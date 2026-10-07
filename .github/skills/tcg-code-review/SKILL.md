---
name: tcg-code-review
description: 'Review TCG Grader changes for correctness, security, regression risk, data integrity, architecture fit, and tests. Use for pull requests, code audits, refactors, new modules, or before merging changes.'
---

# TCG Grader Code Review

Review in this order.

## 1. Merge blockers
- Hardcoded secrets, unsafe shell execution, arbitrary URL/code execution, auth bypass.
- Data corruption, incorrect card identity merges, stale-evidence promotion, grading calibration bypass.
- Runtime claims not backed by tests or device evidence.
- Integrity manifest mismatch or sync-generation mismatch.
- Changes that silently weaken existing fail-closed guards.

## 2. Correctness
- Validate all external inputs and JSON shapes.
- Keep card identity separated by game, card number, set, language, condition, printing, grader, and grade where relevant.
- Do not count mirrors/fallback URLs as independent evidence.
- Make timestamps timezone-aware and freshness windows explicit.
- Avoid boolean-as-integer bugs when validating counts/scores.

## 3. Testing
- Add deterministic tests for success, stale data, malformed input, boundary values, and failure paths.
- Tests must prove the new behavior; do not merely assert file existence.
- Preserve historical successor/sync tests and register a new generation when watched runtime paths change.

## 4. Performance and maintainability
- Avoid repeated full-file scans in hot paths.
- Bound candidate lists, external-source fanout, retry counts, and memory growth.
- Prefer small pure functions for scoring and evidence decisions.
- Reuse registry/runtime contracts instead of introducing duplicate hardcoded catalogs.

## 5. Review output
Classify findings as BLOCKER, IMPORTANT, or SUGGESTION. State file/function, impact, and a concrete fix.
