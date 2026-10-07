---
name: tcg-regression-recovery
description: 'Diagnose and repair TCG Grader CI failures, sync-lineage failures, integrity mismatches, regressions, and runtime guard failures. Use when tests fail, a workflow pauses, a successor generation is stale, or a patch needs recovery.'
---

# Regression and Recovery

## Workflow
1. Read the latest branch head and check-runs; never debug an old SHA as if it were current.
2. Group failures by root cause: syntax, functional test, sync lineage, integrity manifest, workflow policy, environment/device.
3. Inspect the smallest relevant logs first.
4. Reproduce the contract logically from current files and commit ancestry before changing tests.
5. Fix production behavior first. Fix tests only when the contract is genuinely outdated.
6. For watched runtime changes, create a new successor generation instead of weakening old generation assertions.
7. Recompute exact SHA-256/byte metadata after every tracked-file change.
8. Run targeted tests -> Main SELFREFINE -> Alignment/Integrity -> Deep -> Exhaustive when applicable.

## Guardrails
- Do not delete failing tests merely to get green CI.
- Do not widen allowed watched-path sets without proving the exact changed paths.
- Do not mark physical tablet verification true from CI.
- Keep last-good/rollback paths intact.
- Report partial PASS accurately; do not say "all PASS" while long-running checks are pending.
