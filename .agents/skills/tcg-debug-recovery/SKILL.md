---
name: tcg-debug-recovery
description: Use whenever a TCG Grader test, workflow, collector, tablet job, Windows task, SELFREFINE cycle, or runtime behavior fails or becomes intermittent.
---

# TCG debugging and recovery

1. Preserve evidence first: failing command, workflow/job/step, error code, input class, timestamp, and last-known-good commit.
2. Reproduce with the narrowest deterministic command possible.
3. Localize the failing layer: source collection, parsing, OCR/vision, grading/calibration, market data, autonomy, UI, scheduling, device/runtime, or CI.
4. Separate primary failure from secondary noise. Fix the root cause, not the final exception only.
5. Compare against last-known-good behavior or use commit/PR diff history when regression timing is known.
6. Add a regression test or guard that fails on the original defect.
7. Recovery order:
   - targeted repair;
   - targeted test;
   - subsystem regression;
   - full/current runtime verification;
   - output validation;
   - only then resume autonomous mutation.
8. Network failures must respect bounded retries, Retry-After, cooldown, response-size limits, HTTPS/source allowlists, and rate limits.
9. Corrupt state must fail closed. Do not silently reset learned state unless the existing schema explicitly permits a verified recovery path.
10. Record a stable error category and remediation outcome so repeated failures can be grouped instead of rediscovered.
