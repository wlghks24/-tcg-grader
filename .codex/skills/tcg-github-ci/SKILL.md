---
name: tcg-github-ci
description: Safely make GitHub repository changes for TCG Grader using protected branches, PRs, scoped CI, minimal-inline workflows, integrity manifests, workflow security, exact-SHA verification, and merge gates.
version: "1.1.0"
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

## Minimal-inline workflow discipline
Keep workflow YAML declarative. Prefer `uses:` entries and short script entrypoints over embedded shell/Python logic.

Use this order:
1. One trivial command used once -> a short `run:` line is acceptable.
2. Multi-command validation, parsing, loops, conditionals, heredocs, fixtures, or recovery logic -> move it to a versioned repository script such as `scripts/ci/<name>.py` or `scripts/ci/<name>.sh`.
3. A repeated group of steps inside jobs -> use a repository-local composite action under `.github/actions/<name>/action.yml`.
4. A repeated whole job/workflow -> use a reusable workflow with `workflow_call`.
5. Agentic/shared prompt components -> prefer imported/shared components instead of duplicating large inline blocks.

For every new or materially changed workflow:
- Do not add Python or JSON heredocs directly inside `run: |`.
- Do not embed generated files, fixture source, or long shell programs in YAML.
- Keep shell branching and recovery logic in tested scripts.
- Keep duplicated command blocks out of multiple workflows; centralize them once.
- Pass untrusted GitHub context through environment variables or validated script inputs rather than interpolating it into executable shell text.
- Keep local actions/workflows small enough that their behavior can be reviewed without scrolling through unrelated logic.
- A justified exception must stay short, be single-purpose, and explain why extracting it would reduce clarity.

## Refactor rule
When touching a legacy workflow that already contains a large inline block, reduce inline surface in the edited area instead of expanding it. Do not perform a risky repository-wide rewrite solely to satisfy style; migrate incrementally behind existing tests.

## Workflow safety
- Use least-privilege `permissions`.
- Pin third-party Actions to repository-approved immutable revisions.
- Do not put secrets into pull-request-controlled commands or logs.
- Keep generated/untrusted text out of executable shell/script contexts.
- Do not add direct-main self-modification to autonomy controllers.
- Prefer repository-owned scripts and local composite actions over downloading execution logic at runtime.

## Verification for workflow refactors
- Run the extracted script directly with deterministic fixtures where practical.
- Run `actionlint` on changed workflow files.
- Run the repository workflow-security/zizmor gate when workflow execution surfaces change.
- Confirm local composite actions and reusable workflows are referenced from the intended repository path.
- Compare behavior before/after for exit codes, outputs, permissions, and failure semantics.
- Verify the exact PR head SHA, not an older successful run.

## Version discipline
- A GitHub PR number is not a software version.
- Derive active versions from runtime files, launch routes, contracts, and merged code.
- When Tablet and TCG versions differ, report both explicitly.
- Repository merge proves source integration only; physical tablet installation requires device-side evidence.

## Failure policy
Never "fix CI" by deleting safety tests, widening verification gates, suppressing integrity failures, or treating a skipped check as a pass.
