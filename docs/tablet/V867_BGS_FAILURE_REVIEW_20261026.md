# V867 BGS failure classification and bounded request reuse

## Scope and acceptance

Runtime-only successor based on main `d855b6b09cc3a79419656a5140705272b1671969`.
PR #863 remains stacked on unmerged static snapshot #861; this change imports neither
snapshot. No collected JSON, collection timestamps, last-good facts, models, updater,
Termux schedule, grading calibration or deployment configuration changes.

## Confirmed defects and changes

1. The base watcher retains last-good source dictionaries, including yesterday's
   `failure_class`. Fresh 403s could lack classification, and a 403/503/timeout could
   inherit planned maintenance. Classify exact 403 diagnostics per BGS source as
   `access_denied_unverified`; an unrelated failure cannot retain planned maintenance.
   An actual Beckett maintenance redirect remains separately classified. Facts and
   verification status are never promoted by this classification.
2. Failed exact-URL requests were repeated within one collection transaction, including
   a canonical BGS status recheck after a blocked pricing request. Reuse only the
   failure diagnostic for that transaction. A new collection always attempts again.
   CGC keeps at most one same-URL transient retry; 403/429 remain non-retryable.
   New attempt/failure-cache counters distinguish actual network work from successful
   response counts. No response body is fabricated or persisted.
3. Old CGC byte pins rejected any runtime correction. A separate V867 capsule proves
   the exact source candidate, changed paths, original V563 baseline, unchanged
   intervening source, live source/test hashes and candidate ancestry. Original
   historical pins and older visible changes remain intact. No data snapshot receives
   authorization from this capsule.

## Review and verification

- New behavioral regressions fail against the previous production implementation.
- 37 focused tests pass: BGS/TAG/CGC behavior, last-good retention and six independent
  successor negative tests. Cache warmup cannot hide changed live bytes, forged flags,
  symlinks or divergent HEAD history.
- Deterministic duplicate-failure check: two calls to the same blocked BGS URL require
  one requester invocation; exhausted CGC calls require two rather than four. These
  are request-count measurements, not physical-tablet latency measurements.
- Existing Main SELFREFINE, alignment, integrity, Deep/Exhaustive and CodeQL must be
  verified on the final PR head. Local results are recorded in the PR description.
- Physical Lenovo readback, screen rendering and actual runtime lag remain unverified.
  `physical_tablet_runtime_verified=false`, `deployment_allowed=false`.

## Cross-review conclusions

Correctness: classification follows each current error, not a sibling or old label.
Security: allowlists, redirects, retry limits, evidence/publish gates are preserved.
Performance: repeated failures are bounded within the existing transaction, with no
new scheduler, dependency, cloud runtime or persistent cache.
Lineage: V563 and V641 historical proofs remain unchanged and must continue passing.

No overall quality score or device PASS is inferred from unit-test counts. The
merge decision depends on current-head required CI; deployment requires device proof.
