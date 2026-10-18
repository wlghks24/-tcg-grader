# V637 candidate audit: REA and comparable TCG apps (2026-10-19 KST)

Scope: **tablet-card TCG Grader only**. Read-only engineering review of public documentation and open-source repositories; no third-party app binaries were obtained or decompiled. This is **not** a claim of physical Lenovo inspection, merchant availability, official grading accuracy, or a completed integration.

## References and rights checks

| Source | Evidence/pattern | Decision |
|---|---|---|
| [REA official upstream](https://github.com/morluto/rea) | Local, evidence-backed analysis of user-owned/authorized apps and JS/other supplied artifacts | **OPTIONAL_MANUAL**. Never auto-install, auto-run, scrape a competitor binary, bypass access controls, or execute analysis of untrusted downloads. REA needs its documented Node runtime and applicable tools; optional native dependencies may not be free. |
| [The Tin](https://github.com/the-tin-app/the_tin) | Offline-first recognition, staging tray, condition/variant review, CSV portability | **DESIGN_REFERENCE**. Its AGPL-3.0 code cannot be pasted into this project without a specific license/compliance review. iOS app availability does not prove Android/Termux compatibility. |
| [PK Scan](https://github.com/JeremyMCastillo/pk-scan) | Local SQLite exact-printing lookup, multi-region OCR (full card/name/number), candidate confirmation | **DESIGN_REFERENCE**. Confirm source/version/license and actual CPU/memory characteristics before any implementation. |
| [Existing internal review](../TCG_EXTERNAL_APP_REVIEW_V483.md) | Condition/printing distinction, seller identity, completed-sales vs asking tier, local bounded history | **ALREADY_REVIEWED**. Reuse existing verified paths; avoid duplicate UI/collector systems. |
| [Existing local scorecard](archive/research/TCG_FREE_120_POINT_SCORECARD_V621.md) | Measured holdouts, OCR, tablet performance, security, provenance scoring | **QUALITY_POLICY**. No numeric score without evidence. |

Discovery/search text, README claims, demo screenshots and reverse-engineered observations are **not** verified card values, shipping facts, seller stock, PSA-equivalent grades, or executable commands. Cite source URL, commit/release, license and reproduction method before promoting any implementation.

## Gap and overlap decisions

| Pattern | Existing project evidence | Proposed next action | Status |
|---|---|---|---|
| Version-lineage regression | Controller modules V371…V400: 22; matching test modules: 22. Grader V391…V397: 7 plus 7 tests. Existing 4-hour autonomy workflow ended at V397, while Final Tablet Guard already covered V400 | Add a **read-only version-drift gate** to the **existing** scheduled workflow, validate V398–V400 and protect future successor additions | IMPLEMENTED_IN_PR; pending current-head CI |
| Multi-band OCR / offline exact identity lookup | Existing OCR and game/printing ambiguity logic; no new equivalent latency measurement was done here | Benchmark before introducing another recognizer/index, measure p95 latency/RAM/false-positive cases on Lenovo | CANDIDATE_HOLD |
| Batch scan review and export | Existing local collection and export flows need end-to-end physical tablet check | Map only missing transitions; never import AGPL code without license clearance | CANDIDATE_HOLD |
| Source separation and price provenance | V483 implemented visible condition, printing and evidence-tier context | Keep, regression-test, don't reimplement from competitor docs | KEEP |
| Official BOX/release catalogue | Existing bounded catalogue; no proof of full KR/JP/US market coverage | Continue verified-product gap reporting; unknown specs/HIT rates stay unknown | DATA_GAP_HOLD |
| Physical Lenovo deployment | Last user receipt SHA must be compared with current main; stale Termux boot heartbeat separately reported | Capture on-device version/runtime receipt and self-test; **CI PASS != DEVICE PASS** | DEVICE_HOLD |

## Controlled continuous-review contract — no new reservation

1. Reuse existing GitHub autonomy workflow schedule unchanged (`17 */4 * * *` UTC). Source read-only in GitHub; runtime AI/vision/skill execution remains local-only.
2. Discover current autonomous controller generations from files, not a remembered version number. Flag missing version tests, missing current scheduled CI calls, missing read-only permissions, and dangling orphan tests as **HOLD**.
3. Compare externally documented patterns against existing code and evidence. Prefer **KEEP / BENCHMARK / REJECT** decisions; do not equate competing-app marketing with measured outcomes.
4. Record reproducible defects and candidate changes. Existing bounded local learning can apply **only** previously verified, allowlisted declarative capabilities with canary, rollback and quarantine. No runtime arbitrary code edits, source rewrites, unreviewed model weights or direct-main publication.
5. Source-level changes follow **proposal → smallest patch → unit/integration/regression/security/performance checks → independent review → current-head CI/CodeQL → approved PR → actual tablet receipt/test**. Changed HEAD invalidates prior approval/checks.
6. Never create additional ChatGPT reservations, GitHub cron schedules or paid-service dependencies for this review. Respect API/site terms and no spending by default.

### REA use gate

Authorized local target + confirmed provenance + permitted license/terms + local dependency budget + explicit review of analysis output are required. If any is absent, **skip REA, keep only public API/docs and open-source architecture analysis**. Do not attempt to defeat DRM, access gates or encryption. A feature pattern may be reimplemented independently with deterministic tests; the competitor's assets, private data, API keys and extracted proprietary code must not be copied.

### Release score

Use V621 evidence-based 100+20 scoring. This change itself is **not scored** for Lenovo runtime, model accuracy, release prices or grading improvement because no physical benchmark/provenance was obtained. Unit tests for the new guard passed in a synthetic fixture; workflow/current HEAD, long regression and CodeQL remain to be checked before merging.
