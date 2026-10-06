---
applyTo: "**"
---

# TCG Grader repository instructions

Use the repository-owned project skills under `.agents/skills/` or the byte-identical `.codex/skills/` mirror before changing code.

## Skill routing

- behavior change, bug fix, refactor, parser, autonomy, OCR, grading, market, or UI logic → `tcg-test-driven-regression`
- failing test, broken workflow, flaky collector, runtime incident, SELFREFINE failure → `tcg-debug-recovery`
- every PR/diff before merge → `tcg-code-review`
- Python implementation/refactor/state handling → `tcg-python-quality`
- external input, network, file, subprocess, credential, dependency, workflow security → `tcg-security-review`
- invariant/state-machine/parser/property coverage → `tcg-property-testing`
- GitHub branch/PR/workflow/integrity/release work → `tcg-github-ci`
- latency, memory, CPU/GPU, storage, polling, batching, concurrency, image cost → `tcg-performance-budget`
- logs, diagnostics, retry/recovery evidence, operational telemetry → `tcg-observability`
- OCR, card image, 1→4→8 analysis, defect detection, grading calibration → `tcg-vision-grading`
- external docs/APIs, market/release/promo/purchase sources, provenance/freshness → `tcg-source-evidence`

## Repository-wide rules

1. Re-read current main and inspect neighboring code, tests, workflows, sync contracts, and Graphify/code-map guidance before editing.
2. Verification sequence is targeted tests → related regression → current/full runtime checks → actual output validation. Do not weaken tests or fail-closed guards to make CI pass.
3. TCG Grader ↔ Tablet GPT mutual-sync is local-only. Do not add cloud learning or cloud parallel learning unless the user explicitly reverses that requirement.
4. Never invent prices, grades, stock, release/event facts, market direction, source verification, physical tablet results, or Drive/device readback.
5. Autonomous runtime code may select only existing allowlisted declarative capabilities. New source-level functionality requires normal branch/PR/CI review.
6. Preserve protected boundaries: do not exchange raw peer weights, grading calibration, secrets, private runtime state, or unverified learned text as executable authority.
7. Treat network/file/web/model input as untrusted. Keep HTTPS/source allowlists, bounded reads/responses, rate-limit/retry/cooldown, strict schema, atomic write, and path-containment rules.
8. GitHub changes use protected branches/PRs, least privilege, pinned Actions, exact-head verification, and required status checks. Autonomous direct-main writes are forbidden.
9. Keep runtime state separate from source truth. Missing, stale, corrupt, contradictory, or low-confidence evidence must degrade/hold instead of fabricating confidence.
10. Before merge apply `tcg-code-review` and `tcg-github-ci`; required checks must complete successfully.
