---
name: tcg-ci-release
description: Use when changing GitHub Actions, release flows, branch/PR behavior, scheduled jobs, deployment/update scripts, integrity manifests, or merge requirements.
---

# TCG CI and release

1. Work on a branch; do not push autonomous source changes directly to main.
2. Keep changes atomic and reversible. Separate functional code from unrelated cleanup.
3. Pin external GitHub Actions to immutable commit SHAs and use least-privilege permissions.
4. Quality gates should fail closed on test, integrity, security, sync-contract, or actual-output failures.
5. Never make a red pipeline green by skipping tests, widening freshness windows, suppressing integrity checks, or converting required gates to advisory.
6. Scheduled jobs must use concurrency controls where duplicate mutation could corrupt state.
7. Preserve last-known-good/rollback behavior for runtime-delivery changes.
8. Before merge confirm:
   - targeted tests green;
   - related regressions green;
   - repository integrity/security green;
   - Tablet GPT ↔ TCG Grader alignment green when watched paths changed;
   - no stale required contract.
9. Merge only when required checks are complete and successful.
10. After merge, verify the new main commit and any push-triggered critical workflow that validates the changed surface.
