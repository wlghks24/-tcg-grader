# Grading source reintegration v241

Cross-validation summary for the current grading-source hardening stack.

- TAG official service collection parser is bounded per tier.
- TAG structured product-offer fallback is fail-atomic and remains on official taggrading.com hosts.
- PSA overlapping service aliases are bounded to prevent Value/Value Max and Express/Super Express leakage.
- BGS current-layout parser requires the complete tier table and handles Base/Subgrades separately.
- Provider parser revisions are isolated: PSA US/JP and BGS US use revision 3; unchanged providers retain the global parser revision.
- Transport retry is bounded to one retry for transient timeout/connection reset/HTTP 502/503/504 only. HTTP 401/403/404/429 and host-policy denials are never retried or bypassed.
- Source failures are classified and last-good official data remains fail-closed.

External status observed during cross-validation on 2026-09-15:
- PSA official grading endpoints returned HTTP 403 to GitHub-hosted collection.
- Beckett legacy beckett.com grading/news routes redirected outside the current allowlist; no allowlist widening was performed without an explicit verified source migration.
- TAG legacy page parser yielded zero services, motivating the official structured-offer fallback.

These external states must not be converted into healthy source status by retry loops, host bypasses, or test weakening.
