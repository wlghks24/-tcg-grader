# Workflow debt cleanup v242

## Scope

This cleanup is stacked on `audit/tablet-source-reintegration-v240` and does not change production/runtime source code or data outputs.

## Before

Read-only audit run `34965745497` classified `.github/workflows/apply-*.yml` / `.yaml` as follows:

- apply workflows: 68
- manual write/push debt: 63
- explicitly marked legacy integrated write/push workflows: 62
- broken legacy mutators: 1
- workflows that directly pushed to `main`: 31
- duplicate version families: 3
- workflows referencing a missing helper: 1

The one broken legacy mutator was `apply-collection-meta-learning.yml`, which referenced a missing helper. No unmarked write/push workflow required separate retention review.

## Change

Removed only the 63 `apply-*` workflow entrypoints that could write and push repository contents. Their helper/patch scripts were intentionally retained for local/manual recovery and historical inspection.

No collector, grader, UI, server, learning state, public JSON, source allowlist, test threshold, or fail-closed rule was removed or weakened.

## Preserved read-only validators

The following five `apply-*` workflows remain because they are validation jobs with `contents: read` and do not push source changes:

- `apply-auto-validation-flow.yml`
- `apply-detailed-collection-intelligence.yml`
- `apply-eight-zone-runtime-compat-v158.yml`
- `apply-pending-official-candidate-v161.yml`
- `apply-retry-reason-ui-v160.yml`

## After

Read-only audit run `34965994692` on cleanup commit `142d56c27d0048f310b5bc5414ce591d021d281d` reported:

- apply workflows: 5
- manual write/push debt: 0
- legacy integrated write/push workflows: 0
- broken legacy mutators: 0
- write/push workflows needing review: 0
- direct `main` push workflows: 0
- duplicate version families: 0
- missing-helper workflows: 0

The audit artifact digest recorded by GitHub Actions is `sha256:e1be056d07516680dbf2cd10f797dc177c1d3292f1f8251699f4207dd4f1197c`.

## Safety boundary

This cleanup must not be used to bypass the existing PSA/BGS external-source fail-closed condition. PR #147 remains the integration gate for `main`.
