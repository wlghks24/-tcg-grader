---
name: tcg-mistake-proofing
description: Convert recurring TCG Grader mistakes into structural fail-closed controls so invalid states, unsafe updates, unsupported grading, stale evidence, and accidental runtime changes become hard or impossible to express.
version: "1.0.0"
---

# TCG Mistake Proofing

Use when the same class of bug can recur even after documentation or a one-off patch.

## Control ladder
Prefer, in order:
1. Control: make the invalid action impossible.
2. Warning: block immediately with a deterministic guard.
3. Detection: catch it in tests or monitoring after the fact.
4. Documentation alone is not a sufficient final control for recurring defects.

## TCG examples
- Unsupported games cannot become grading-enabled without an explicit calibrated capability.
- WATCH entries cannot silently become live-purchase or grading targets.
- Runtime-generated state cannot masquerade as immutable source truth.
- Update logic cannot overwrite tracked source when dirty state is outside the approved runtime allowlist.
- A stale scheduler heartbeat cannot be treated as healthy solely because a PID exists.
- A new PWA asset cannot ship without runtime/cache delivery coverage.
- A UI category cannot expose every long detail panel merely because targets share a category.
- External evidence cannot become verified price/release/stock truth without source/freshness gates.

## Review questions
- What mistake remains expressible after this patch?
- Where is the earliest boundary that can reject it?
- Can the guard be bypassed by missing data, defaults, retries, or stale state?
- Is the invariant represented in code/test/schema rather than only prose?

## Local-only boundary
Mistake-proofing must work in the local tablet/runtime architecture and must not depend on cloud policy engines or remote control planes.
