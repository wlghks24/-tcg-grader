---
name: tcg-observability
description: Use when adding or changing TCG Grader collectors, retries, scheduled jobs, autonomy, SELFREFINE, OCR/grading pipelines, or any production/runtime path that must be diagnosable.
---

# TCG observability

1. Define what an operator needs to know: what failed, where, why, whether recovery ran, and whether output remains trustworthy.
2. Emit stable machine-readable event/error categories instead of free-form-only messages.
3. Include bounded context such as subsystem, operation, source/provider, attempt, duration, gate/status, and correlation/run ID.
4. Never log secrets, tokens, cookies, full credentials, or unnecessary personal data.
5. Record retry/cooldown reasons separately from terminal failures.
6. Distinguish degraded-but-usable from fail-closed/blocked states.
7. For autonomy, record selected action, upstream gate, evidence class, hold reason, state-write outcome, and rollback result.
8. For collection, track success/failure counts, freshness, source-health, latency, and bounded response size.
9. Alerts or automatic recovery should trigger on user-impacting or trust-impacting symptoms, not noisy implementation details.
10. A new recovery rule is incomplete until logs/tests can prove both activation and successful/failed recovery outcomes.
