---
name: tcg-code-review
description: Use before merging every TCG Grader PR or when reviewing AI-generated changes. Review correctness, maintainability, architecture, security, performance, and verification evidence.
---

# TCG code review

Review the tests first, then the implementation and workflow changes.

Check six axes:
1. Correctness: intended behavior, edge cases, error paths, stale/missing data, state transitions.
2. Readability: simple control flow, clear names, no unnecessary duplicate helpers or version drift.
3. Architecture: keep grading, market, Instagram, tablet/runtime, and SELFREFINE domain boundaries intact.
4. Security: external input is untrusted; no secrets, arbitrary commands, unsafe paths, unbounded downloads, or permission expansion.
5. Performance: no unbounded loops/fetches, avoid heavy work on latency-sensitive tablet/Windows runtime paths.
6. Verification: focused tests plus related regression and output validation are present and meaningful.

Block merge for:
- verification bypass or weakened fail-closed behavior;
- direct-main mutation added to autonomous code;
- invented price/grade/market facts;
- raw model/state/calibration exchange across protected boundaries;
- unreviewed source-generation or arbitrary-command capability;
- failing required CI.

Prefer small, reversible changes. If a PR mixes independent concerns, split it before merge.
