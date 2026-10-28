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
