---
name: tcg-github-ci
description: Safely make GitHub repository changes for TCG Grader using protected branches, PRs, scoped CI, integrity manifests, workflow security, exact-SHA verification, and merge gates.
version: "1.0.0"
---

# TCG Grader GitHub / CI

## Change flow
1. Re-read current `main` immediately before starting; do not rely on an earlier chat snapshot.
2. Create a branch from the exact current main.
3. Make the smallest coherent change.
4. Run targeted tests first.
5. Update `integrity_manifest.json` after final file contents are stable when protected tracked files require it.
6. Open a PR and verify the exact head SHA.
7. Wait for all relevant protected guards; inspect the failing step instead of weakening tests.
8. Merge only when the PR is mergeable and required checks pass.
9. Re-read main after merge.

## Workflow safety
- Use least-privilege `permissions`.
- Pin third-party Actions to repository-approved immutable revisions.
- Do not put secrets into pull-request-controlled commands or logs.
- Keep generated/untrusted text out of executable shell/script contexts.
- Do not add direct-main self-modification to autonomy controllers.

## Version discipline
- A GitHub PR number is not a software version.
- Derive active versions from runtime files, launch routes, contracts, and merged code.
- When Tablet and TCG versions differ, report both explicitly.
- Repository merge proves source integration only; physical tablet installation requires device-side evidence.

## Failure policy
Never "fix CI" by deleting safety tests, widening verification gates, suppressing integrity failures, or treating a skipped check as a pass.
