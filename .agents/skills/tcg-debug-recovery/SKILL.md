---
name: tcg-debug-recovery
description: Diagnose and repair TCG Grader failures systematically. Use for failed tests, broken workflows, flaky collectors, SELFREFINE incidents, tablet/Windows runtime faults, or unexpected behavior.
version: "1.0.0"
---

# TCG Grader Debugging and Recovery

1. Preserve evidence first: failing command, workflow/job/step, stable error code, timestamp, input class, environment, and last-known-good commit.
2. Reproduce with the narrowest deterministic command possible.
3. Localize the owning layer: collection, parsing, OCR/vision, grading/calibration, market data, autonomy, UI, scheduling, device runtime, or CI.
4. Separate the primary failure from secondary noise and fix the root cause rather than the final exception only.
5. Compare against last-known-good behavior or commit history when regression timing is known.
6. Add a regression test or guard that fails on the original defect.
7. Recovery sequence is targeted repair → targeted test → subsystem regression → full/current runtime verification → output validation.
8. Network recovery must keep bounded retries, Retry-After/cooldown handling, HTTPS/source allowlists, response-size limits, and rate-limit protections.
9. Corrupt trusted state fails closed. Do not silently reset a champion/model/state unless the existing schema explicitly permits a verified recovery path.
10. Record a stable error category and remediation outcome so repeated incidents can be grouped and learned from safely.
