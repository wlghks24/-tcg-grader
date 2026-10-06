---
name: tcg-code-review
description: Review TCG Grader changes before merge with correctness, security, data, performance, architecture, test, UI/PWA, and operations lenses. Use for PRs, diffs, commits, release changes, or "review before merge".
version: "1.0.0"
---

# TCG Grader Code Review

Use this project-specific review flow instead of a generic checklist.

## 1. Bound the change surface
- Start with `python code_map_fast_route.py "<feature>" --impact` when the feature is known.
- Read the actual changed files after routing; Graphify output is navigation evidence, not source truth.
- Expand to repository-wide search only when routing reports an unknown feature or the diff crosses a protected boundary.

## 2. Review independently through these lenses
1. Correctness: contracts, edge cases, malformed/empty data, state transitions.
2. Security: secrets, shell/URL/path injection, unsafe deserialization, arbitrary commands, authorization or verification bypass.
3. Evidence/data: verified/unverified separation, provenance, deduplication, freshness, fail-closed behavior.
4. Grading: 1→4→8 vision integrity, finite bounded outputs, company-specific calibration, no invented grades.
5. Market: source health, KR/JP/US coverage, no invented price/stock/release/event facts or directional prediction.
6. Performance: bounded loops, retries, I/O, memory, background work, tablet headroom.
7. Architecture: Tablet GPT / TCG Grader / Instagram isolation, runtime-state vs source-truth separation.
8. Tests/operations: targeted tests, regression coverage, rollback/recovery, CI permissions and integrity manifest.

## 3. Validation depth
- Low: targeted tests for the owning feature.
- Medium: targeted tests + repository verification relevant to the changed boundary.
- High/Critical: targeted tests → full regression → output validation → integrity/security guards.
- Any workflow, security, critical runtime, domain-boundary, or integrity change is at least High.

## 4. Required review findings
Prioritize concrete defects. Each finding should state:
- severity,
- affected path/function,
- failure mode,
- evidence,
- minimal safe fix,
- missing regression test.

Do not approve a change merely because tests pass. Do not claim a device-side install or runtime state without device evidence.
