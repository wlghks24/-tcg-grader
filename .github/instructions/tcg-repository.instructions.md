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
- verified game/set/era, card number and generation display without unsupported inference → `tcg-card-context`
- external docs/APIs, market/release/promo/purchase sources, provenance/freshness → `tcg-source-evidence`
- card/BOX price age, stale/expired evidence, observation dates, freshness confidence → `tcg-market-freshness`
- printing/parallel/artwork/set/language ambiguity and explicit variant confirmation → `tcg-card-variant-resolution`
- local CSV/JSON evidence export, user-owned backups, safe download snapshots → `tcg-local-evidence-export`
- condition/language/edition/printing-specific raw pricing and exact comparability → `tcg-condition-language-pricing`
- marketplace, seller/store, listing URL, and source lineage display/export → `tcg-seller-provenance`
- official/market/map seller discovery, stock verification, nearby sources and grading→purchase handoff → `tcg-purchase-evidence`
- bounded local price snapshots, recent measurements, and honest device-only trend labels → `tcg-local-price-history`
- Android/Termux install, update, boot, local server, rollback, device verification → `tcg-android-termux-deployment`
- collectors, queues, retries, rate limits, fallback, lineage dedup, differential collection → `tcg-collector-resilience`
- JSON/runtime schemas, migrations, producer-consumer compatibility, persisted-state contracts → `tcg-data-contracts`
- neural/OCR/grading/ranking evaluation, holdout, calibration, drift, champion-challenger → `tcg-ml-evaluation`
- tablet navigation, responsive layout, touch/readability, category focus, honest loading/state UX → `tcg-tablet-ui-ux`
- rendered/local-browser UI behavior, click flows, viewport checks, console/runtime UI errors → `tcg-local-browser-qa`
- before/after tablet screenshots, clipping/overflow/layout visual regressions → `tcg-visual-regression`
- final user-facing tablet polish, category-first hierarchy, accessibility, touch finish → `tcg-ui-finish-gate`
- missing/weak tests or proving a risky change has sufficient behavior coverage → `tcg-test-gap-audit`
- recurring bug classes, invalid states, fail-closed structural prevention → `tcg-mistake-proofing`
- service worker, PWA cache ABI, stale assets, install/update/offline app-shell behavior → `tcg-pwa-runtime-audit`

## Repository-wide rules

1. Re-read current main and inspect neighboring code, tests, workflows, sync contracts, and Graphify/code-map guidance before editing.
2. Verification sequence is targeted tests → related regression → current/full runtime checks → actual output validation. Do not weaken tests or fail-closed guards to make CI pass.
3. TCG Grader ↔ Tablet GPT mutual-sync and skill execution are local-only. Do not add Colab, cloud compute/training, hosted browser/device farms, cloud rendering, or cloud parallel learning. A future cloud path requires a new explicit user request and separate reviewed change.
4. Never invent prices, grades, stock, release/event facts, market direction, source verification, physical tablet results, or Drive/device readback.
5. Autonomous runtime code may select only existing allowlisted declarative capabilities. New source-level functionality requires normal branch/PR/CI review.
6. Preserve protected boundaries: do not exchange raw peer weights, grading calibration, secrets, private runtime state, or unverified learned text as executable authority.
7. Treat network/file/web/model input as untrusted. Keep HTTPS/source allowlists, bounded reads/responses, rate-limit/retry/cooldown, strict schema, atomic write, and path-containment rules.
8. GitHub changes use protected branches/PRs, least privilege, pinned Actions, exact-head verification, and required status checks. Autonomous direct-main writes are forbidden.
9. Keep runtime state separate from source truth. Missing, stale, corrupt, contradictory, or low-confidence evidence must degrade/hold instead of fabricating confidence.
10. Before merge apply `tcg-code-review` and `tcg-github-ci`; required checks must complete successfully.
