---
name: tcg-observability
description: Make TCG Grader runtime and recovery behavior diagnosable. Use when adding collectors, retries, schedules, autonomy, SELFREFINE, OCR/grading pipelines, or any path that needs stable operational evidence.
version: "1.0.0"
---

# TCG Grader Observability

1. Define the operator questions first: what failed, where, why, whether recovery ran, and whether output remains trustworthy.
2. Emit stable machine-readable event/error categories rather than free-form-only messages.
3. Include bounded context such as subsystem, operation, provider/source, attempt, duration, gate/status, and correlation/run ID.
4. Never log secrets, tokens, cookies, credentials, private keys, or unnecessary personal data.
5. Distinguish retry/cooldown, degraded-but-usable, recovered, and fail-closed terminal states.
6. Autonomy telemetry should include selected action, upstream gate, evidence class, hold reason, state-write outcome, and rollback outcome.
7. Collection telemetry should include freshness, source health, latency, bounded response size, and success/failure counts.
8. Keep labels/cardinality bounded; unbounded IDs and raw URLs belong in bounded diagnostic logs, not metric dimensions.
9. Automatic recovery should react to trust-impacting or user-impacting symptoms, not noisy implementation details.
10. A new recovery rule is incomplete until tests/logs can prove both activation and successful/failed recovery outcomes.
