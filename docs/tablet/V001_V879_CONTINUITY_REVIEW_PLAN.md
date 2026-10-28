# TCG Grader V001–V879 — evidence-first historical review, continuity and successor plan
**Date:** 2026-10-28 KST. **Status:** DRAFT / NO MERGE / NO LENOVO INSTALL.
**Main SHA (source snapshot):** `6c78831bbb6e188717f86ef90243a836d2e0b67a`.
**Latest numbered tablet-feature draft currently evidenced:** V879 at draft PR #896, not proven merged or device-installed.
**Parent reviewer:** PR #902 (9 historical *inventory* windows, exact-head 23/23 CI success).
**Consolidated observations:** Issue #901. Candidate grading fix: PR #903 (watched source, requires new reviewed successor).
**Independent watched-path warning:** PR #904; this is a tool version, **not proof of V880–V904 released features**.

## 1. Exact 100-version windows
| Window | Inclusive target versions | Provenance/evidence limitations | Quality status |
|---|---|---|---|
| W001 | V001–V100 | Earliest Git root is V31-era; V001–V030 have no verified original Git snapshot. V99 named source was revised by successors. | NOT AUDITED |
| W101 | V101–V200 | V101–V109 saved historical reports; old verify scripts can write files/start server. Never execute as a read-only scan. | NOT AUDITED |
| W201 | V201–V300 | V291 historical corrective behavior; tests ≠ full implementation proof. | NOT AUDITED |
| W301 | V301–V400 | Must connect runtime, learner, tests and protected sync ancestry separately. | NOT AUDITED |
| W401 | V401–V500 | Protected V426 prefix watch may mark unrelated new grading/runtime changes as a successor requirement. | NOT AUDITED |
| W501 | V501–V600 | Full source/contract/test relationship needs separate verification. | NOT AUDITED |
| W601 | V601–V700 | V645/V646 protected reviewed SHA paths; never relax old hashes. | NOT AUDITED |
| W701 | V701–V800 | No standalone V7xx filename/commit-subject hints on protected main; separate PR-title/branch/body review found no exact V7xx mentions. **Absence of tokens is not proof releases never existed.** | PROVENANCE GAP / NOT AUDITED |
| W801 | V801–V879 | Main contains V865/V867 markers; V879 latest known open feature draft PR #896; PR labels are not installed releases. | NOT AUDITED |

V880–V900 are **outside this verified V879 snapshot**, even though earlier machinery used a V801–V900 100-slot *container*. Future extension must update source HEAD, latest-version evidence and re-run ALL affected checkpoints.

## 2. Review for EACH numeric version (879 slots; do not skip absent records)
1. **Identity and origin** — seek original commit/PR, release artifact, original file SHA, timestamp, branch ancestry, planned scope and known original. Record `PRE_REPOSITORY_UNVERIFIED`, `NO_MAIN_TOKEN_LEAD`, `HINT_ONLY`, `ORIGINAL_SOURCE_REVIEWED` distinctly. Do not infer existence from an integer.
2. **Code map and functional inventory** — map changes to module/entrypoint, caller, data flow, state files, sibling browser/Python/Termux implementation, manifest, network, permissions, and old/new dependencies.
3. **Error, typo, omission and logic review** — examine conditionals, invalid and missing input, duplicate/fresh/stale data, boundary numeric values, type confusion, title encoding, date/year/locale, path mismatch, partial failure, replay, race/lock, leakage, timeout, rollback.
4. **Behavior reproduction** — commit-pinned deterministic unit tests with both positive and negative cases; then integration, semantic security, browser/Termux contract and regression where relevant. **Do not run old apply_* or verify_* scripts with side effects in an inventory process.**
5. **Review and patch** — write a finding with `finding_id`, affected V range, exact source file+function, first-bad commit (if provable), symptom, reproducible test, root cause, risk, proposed fix and reviewer. Confirm prior approved successor before editing watched files. Make a small isolated PR and capture its exact commit/test output.
6. **Score and independent crosscheck** — score only against inspected source and evidence, not existence of file/token or synthetic report `ok: true`. Preserve original failed assertions and immutable SHA pins, and distinguish candidate CI from device state.
7. **Carry forward** — link prior W's checkpoint SHA and all unresolved findings (and earlier resolved findings with proofs) into the next W; record if a later V repairs an earlier V. A repair is recorded as `CANDIDATE` until the exact-HEAD tests and review pass.
8. **Post-review** — replay changed test suites on exact candidate HEAD and compare with last-good. If protected paths changed, add a formally audited successor generation; no forced merge or physical device install.

## 3. Quality scoring contract — out of 100, NOT a guessed number
Award points only after reproducible evidence and an identified reviewer:
| Subscore | Weight | Evidence needed |
|---|---:|---|
| Code origin and version-accurate provenance | 20 | Original source SHA, ancestry, scope |
| Logic and complete intended behavior | 20 | Function-by-function code map, edge cases, observed results |
| Safety, trust and data integrity | 20 | Invalid inputs, permissions, secrets, failure and rollback proof |
| Automated functional + integration tests | 20 | Exact commit, test names/results, negative cases, environment |
| Historical regression and patch/successor continuity | 15 | Exact precursor/patched SHAs, previous finding disposition, old tests not weakened |
| Resource/performance evidence | 5 | Repeatable bounded runtime/storage/memory/latency checks |

**If any category lacks adequate evidence, quality score remains `null / NOT_RATED`, not 0 and not a free PASS.** A critical fail-closed/lineage failure blocks merge regardless of totals. A score of 100 does not certify Lenovo physical execution: `DEVICE_UNVERIFIED` is its own non-negotiable deployment gate. Target ≥95 once independently reproduced, but never fake a score to reach it.

## 4. Source grades and code-review state
Each numeric slot must separately carry: original provenance, file-token leads, commit-title leads, related PR leads, source code reviewed?, behavior test verified?, typo/error/missing assessment, historical link, candidate patch link, CI exact SHA, security/latency measurement, **quality_score** (null by default), device receipt (unverified by default).
Evidence lead ≠ source review ≠ unit test PASS ≠ system PASS ≠ merged release ≠ installed tablet.
The matrix tool uses the nine chained snapshots to enumerate all V001–V879 slots and **explicitly refuses to score or certify code** from filename/commit-title hints. It does not import app code or write tracked files.

## 5. Known grounded continuity edges / priorities
- **P0, V99→V291**: original `grading_accuracy_v99.py` could ignore missing defect channels; later V291 repaired by returning conservative risk 100 on missing evidence. Preserve actual V291 fix; the V99 file name is not proof it still has its original bytes.
- **P0, current V99 Python+JS range issue**: negative defect channels can be clamped to apparent zero risk. PR #903 currently proposes bounds on both `grading_accuracy_v99.py` and `grading_accuracy_v99.js`; the source paths are watched by V426 `grading_`. Targeted candidate success is **insufficient** if Sync/Exhaustive fails; require a genuinely reviewed successor.
- **P0, watched-path drift**: PR #904 proposes fail-closed preflight for V426/V646 contract changes, but is not a successor or proof of all 879 reviews.
- **P1, V101–V200 historical verification**: distinguish historical report/synthetic/mock pass from live social-provider authorization, real image accuracy, and hardware/receipt evidence.
- **P1, V701–V800 provenance gap**: investigate raw branch-only/tag/release/commit-body/archived materials; no invented missing versions or fabricated release dates.
- **P1, V879 unmerged candidate**: review #896 separately against protected main, do not count it as a final installed release.

## 6. Delivery/approval checkpoints
`DESIGN` → `ORIGINAL_VERIFIED` → `SOURCE_REVIEWED` → `TEST_REPRODUCED` → `PATCH_PROPOSED` → `TARGETED_PASS` → `CROSSCHECK_PASS` → `ALL_REQUIRED_CI_PASS` → `REVIEWED_SUCCESSOR_IF_NEEDED` → `MERGE_ELIGIBLE` → `DEVICE_PROOF_IF_APPLICABLE`.

Keep each window's `CARRY_FORWARD` ledger append-only, with unresolved P0/P1 included in all later windows until a reproducible fix closes them. Never overwrite a historical result: mark it `superseded_by` and cite the newer PR/commit/test receipts. Historical source pin conflicts require a *new successor* not recalibration of a previous generation.

### Bounded initial deliverable
Current deliverable is the **audit design + machine-checkable per-version NOT_REVIEWED coverage**, not a false assertion that V001–V879 were all manually analyzed. Quality scores and individual reviewed source claims remain withheld pending evidence. All work stays in `wlghks24/-tcg-grader`; no other project, trading system, Instagram, Android head unit, or Lenovo data is modified.

## 7. Verifiable selected-finding carry-forward (first actual scoped review)
The separate `execution/evidence/version_review_findings_v001_v879.json` ledger contains **10 selected findings**, not a claim of reviewing 879 versions. The `execution/version_review_findings.py` tool resolves its `baseline_main_sha` to the original protected-main Git object, checks every supplied source path's **exact Git blob SHA**, verifies any claimed historical commit exists and is an ancestor of that baseline, and rejects noncontiguous version identities, duplicate IDs, forged scores, unsafe paths and misleading device approval. It does not edit project code or run old `apply_*.py` scripts.

- `W001-F006` and `W001-F007` record historical V99→V135/V291 repairs, as history, not active failures.
- `W001-F009`, `W001-F010` and `W401-F001` carry the unresolved Python/JS malformed defect-risk patch and strict V426 successor requirement. PR #903 is a **blocked candidate** despite its positive targeted Python/JS tests.
- `W101-F005` and `W101-F007` document the exact legacy V101–V109 verification server/JSON side effects and V110/V175 source rewriting; historical verify/apply scripts must not run as read-only inventory.\n- `W601-F001` preserves the reviewed V646 source-hash guard and separate-CI requirement.
- `W701-F001` and `W801-F001` explicitly have **no invented original-source Git blob**: V701–800 provenance remains unknown and V879 is an unmerged draft candidate.
- All unclosed findings are automatically carried into each following window; historical repairs remain in their own separate log. All 879 version scores remain **null** and Lenovo `DEVICE_UNVERIFIED`.

The initial matrix contains exactly 507 version numbers with filename/commit-title hints and 372 without such hints, measured on the pinned original-main snapshot. These are *leads*, not 507 proven releases or passed reviews. No window may claim `COMPLETE` until every numeric slot in that window has a provenance disposition, actual source review (where source exists), cited tests and explicit finding closure/carry. A GitHub CI success only certifies that the ledger and checks are structurally consistent on the tested SHA.

## 8. W001 pinned original-source reconstruction (2026-10-28, forensic subset only)

Forensic checker: `execution/historical_v31_v100_forensics.py`, with independent real-Git regression suite `execution/tests/test_historical_v31_v100_forensics.py`. It reads **actual immutable Git objects**; original application code is not imported/executed, and no web server, physical tablet, or external grader is contacted.

- **V31 source at Git root `6511c822f08685ab13ad3e2588d4bd093874c87b` (2026-08-21):** exactly 8 tracked files. Root `manifest.webmanifest` and `sw.js` reference three PNG icons (`icons/icon-180.png`, `icons/icon-192.png`, `icons/icon-512.png`), but none exist in that commit. Original service worker calls `cache.addAll(CORE)`, so the missing precache assets would prevent a root-only deployment from completing the cache operation. Original V31 report says icon gaps were fixed; **report and original Git package disagree**. Current main has `icon.svg` instead, so this is **historical provenance/packaging evidence**, not a claim the latest tablet PWA is broken. Finding `W001-F012`: open historical execution gap.
- **Original V99 source first imported with V109-era commit `d81711498eb05cfd84a007418cf389970b192197` (2026-08-28):** `grading_accuracy_v99.py` source originally omitted missing defect channels; the reviewed V291 repair `70938e4ce0a99f74dba481eb317bb82e7b917e13` corrected missing-evidence behavior. Later negative/out-of-range input vulnerability remains a separate unmerged candidate (#903); do not confuse history, candidate and production state.
- **V100 report in same V109-era import:** `v100_reference/V100_FINAL_VERIFICATION_REPORT.json` declares `build=...v100...`, but numeric `version=1`; reports 6 passes with synthetic-class samples (12 TP / 24 TN) and `calibration_adopted=false`. Its own limitations say synthetic tests are not a substitute for real graded-card datasets. **Do not convert this into 100% live-photo accuracy or a release grade.** Finding `W001-F013`: open report metadata/provenance discrepancy.
- These additions increase selected W001–W879 finding records from **10 to 12**, with unresolved status carried into following windows by the existing evidence ledger. **879 per-version completed reviews remain 0** pending actual full source+regression evidence. No whole-window quality score is assigned.

Every new finding must cite exact pinned root and current protected-main objects and must remain distinct from post-merge fix proof. Work through W001 first, then W101, W201, etc., following the original eight-step review and review/score gates above.
