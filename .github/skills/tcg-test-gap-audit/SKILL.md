---
name: tcg-test-gap-audit
description: Audit TCG Grader for missing or weak regression coverage around changed behavior, runtime contracts, UI flows, collectors, grading, PWA delivery, and tablet updates without relying on cloud test services.
version: "1.0.0"
---

# TCG Test Gap Audit

Use this skill before calling a risky change complete or when repeated regressions suggest coverage is incomplete.

## Audit method
1. Map changed production files to direct tests, integration tests, runtime guards, and CI workflows.
2. Inspect assertions, not only test filenames or coverage percentages.
3. Confirm happy path plus missing/stale/malformed/duplicate/timeout/rollback/blocked paths where relevant.
4. For UI work, cover initial state, click transition, back/collapse transition, invalid target, and runtime packaging.
5. For collectors, cover retries, rate limits, partial source failure, deduplication, stale evidence, and fail-closed behavior.
6. For PWA/update work, cover cache ABI, new asset delivery, stale-cache recovery, offline fallback where supported, and update compatibility.
7. Rank gaps by user impact and recurrence risk.

## Evidence rules
- A test that only imports or renders code is not proof of behavior.
- Do not count a mocked path as coverage if the mock removes the failure mode being protected.
- Prefer the lowest reliable test layer; use browser/integration tests only where unit/contract tests cannot prove the behavior.
- Never weaken an existing assertion to eliminate a gap.

## Local-only boundary
Use repository tests and local runners. Do not require hosted test grids, cloud device farms, or cloud compute.
