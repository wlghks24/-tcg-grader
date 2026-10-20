# Tablet Code Atlas and Safe Evolution — Audit Plan v1

Status: **inventory and triage only**. This document is not a claim that all repository files or physical-device behaviors have been validated.

## Verified baseline
- Baseline main merge commit: `4c8e210069867f68818661ee93127dce960f5b9c` (PR #759).
- `execution/tablet_code_map_audit.py` provides read-only tracked-file counts, Python AST static imports, reverse references, parse issues, and explicitly sets `physical_device_verified: false`.
- Previous repository smoke reported 1,719 tracked files and 898 Python files. Re-run to refresh; do not assume these counts remain constant.
- The Lenovo Termux device reported local HEAD `ff47c970079b21704ef52d2bc726066455de8789`, many staged/unstaged/untracked changes, and autonomy result FAILED at 2026-10-19 23:00 KST. **Never reset, clean, overwrite or auto-stash this worktree without a verified backup and explicit operator decision.**

## Risk-ranked findings
| Priority | Finding | Evidence | Next action |
| --- | --- | --- | --- |
| P0 | Device working tree contains staged and unstaged source edits and untracked runtime/backup files | Operator-provided `git status --short` | Preserve and inventory local changes; compare upstream only after backup verification |
| P0 | Scheduled updater may attempt main update while local source is modified | `TABLET_SCHEDULED_UPDATE.sh` invokes `ANDROID_UPDATE_AND_START.sh` on SHA mismatch | Review updater preflight/dirty-tree contract; test against isolated fixtures before changing production |
| P1 | V387 rejects training under low verified confidence | Device log: `LOW_VERIFIED_CONFIDENCE`, `HIGH_UNCERTAINTY`, confidence 0.3852 < 0.55, zero verified samples | Preserve fail-closed behavior; investigate evidence acquisition and recovery-only revalidation |
| P1 | Scheduler reports all nonzero autonomy exits as FAILED | `run_autonomy_cycle` in scheduled-update script | Distinguish safe HOLD vs execution error without turning blocked execution into success |
| P1 | Code map is static Python imports only | Analyzer implementation and schema v1 | Add explicit coverage gaps for JS/CSS/HTML, shell entrypoints, dynamic imports, CI, device-only files |
| P2 | Code navigation and regression triage require quicker evidence | Multiple entrypoints and evolving versions | Add reproducible impact report and owner/contract matrix with deterministic tests |

## Code atlas layers
1. **Entry points and scheduler:** `TABLET_SCHEDULED_UPDATE.sh`, `ANDROID_UPDATE_AND_START.sh`, Termux boot integration; record commands, trigger cadence, lock and restart ownership.
2. **Runtime and integrity:** `tablet_runtime_manifest.py`, `integrity_manifest.json`, `.github/workflows/repository-integrity-guard.yml`; track last-good and SHA verification.
3. **Autonomy and learning:** `tablet_autonomous_evolution_v387.py`, `tablet_autonomous_evolution_v400.py`, policy gates, training eligibility, outcome journals; separate advice from execution.
4. **Collectors and market data:** collectors, source registries, releases, events, prices and graded-photo datasets; classify generated mutable data separately from code.
5. **User-facing surfaces:** `index.html`, `sw.js`, JavaScript and CSS; map browser/service-worker dependencies, cache/version migration and rollback.
6. **Tests and CI:** identify tests per changed module, integrity manifest registration and protected checks.

## Repeatable read-only audit
```sh
python execution/tablet_code_map_audit.py
python -m unittest -v tests.test_tablet_code_map_audit
git status --short
git diff --stat
git diff --cached --stat
```
Run in a **clean, disposable checkout** for code review. On Lenovo, start with read-only status only; do not assume local code matches main.

## Automatic daily change-impact detection

The existing `TABLET_SCHEDULED_UPDATE.sh` runs
`execution/tablet_code_map_audit.py --feature tablet --auto-changes`
in the same safe, time-bounded reporting cycle. No separate Termux command or
additional paid service is necessary after an already-working scheduler is
installed. `--auto-changes` uses **read-only Git staged and unstaged tracked
path lists**; it neither stages files nor changes or deletes local material.
It creates `auto_change_inventory_status` (`clean`, `changes`, `unavailable`,
or `over_limit`) and, when needed, `change_impact_plan` for quick source
and test prioritization. Unknown inventory or a truncated set escalates to
full-chain review rather than silently declaring a clean tree. Untracked
device-only scripts are separately inventoried by name and are **not** treated
as analyzed/trusted source.

This report provides investigation leads only. It cannot verify a running
Lenovo device, authorize self-edits or replace CI, Graphify or rollback receipts.

## Maintainer-oriented code map and scoring rules (2026-10-20)

This map groups **existing files by responsibility**. It does not move or delete
them, change user-facing card functionality, or grant the model write access.

| Layer | Canonical route / file | Evidence, boundaries and tests |
| --- | --- | --- |
| Entry + feature discovery | `code_map_intelligence.py`, `code_map_fast_route.py` | Query routing, declared entrypoints, validation plan; optional Graphify use |
| Broad static inventory | `execution/tablet_code_map_audit.py` | Read-only Git-tracked Python AST + conservative quoted shell/web reference candidates; never execute target code |
| Change blast-radius | `--changed-file path` (repeatable) | Reverse-import and literal-link candidate traversal capped at 2 hops by default; bounded modules/tests; unknown/critical paths escalate to full validation |
| Maintenance queue | `maintenance_queue` in scheduled code atlas | P0 dirty tracked worktree, P1 parse/untracked gaps, P2 unresolved static references and missing Graphify artifact evidence |
| Tablet updater | `TABLET_SCHEDULED_UPDATE.sh`, `ANDROID_UPDATE_AND_START.sh` | Dirty-tree HOLD, default runtime JSON preservation, atomic atlas replacement on validated output; verified last-good retained on error |
| Graphify | `GRAPHIFY_UPDATE.sh`, `GRAPHIFY_AUDIT.py` | Artifact existence and CLI presence are **not** extraction proof; physical on-device receipts remain HOLD |
| Tests | `tests/test_tablet_code_map_audit.py`, `test_tablet_scheduled_update_v256.py`, existing CI guards | Negative/HOLD regression, integrity SHA-256, code security and final chain |

**Actual quantitative evidence** from PR-head GitHub Repository Integrity Guard
on `6b09154d735f`: 1,722 tracked paths, 1,712 tracked text files, 900 Python files,
31/31 code-map regression tests, one CI static-audit run of 2,482.336 ms.
These numbers are *not* all-file runtime coverage, a repeated benchmark, or
Lenovo proof. Recheck all counts at the next commit.

**Source inventory vs successfully parsed code:** `python_tracked_count`,
`python_parsed_count`, `python_unscanned_count`, `asset_tracked_count`,
`asset_files_scanned`, and `asset_unscanned_count` explicitly measure scan
coverage. `component_overview` gives up to 32 largest top-level areas with
tracked, Python, test-module and asset counts. No amount of passing static
inspection is represented as unit/integration test coverage.

**Safe developer improvement loop**:
1. Record exact GitHub head, failing job, actual source contract and last-good.
2. Identify first-touch code via feature route; then use static impact **candidates**.
3. Inspect P0 first, reproduce on disposable clean Git fixtures; prefer a
   minimal, reversible change to mass renames.
4. Require explicit negative and HOLD regression tests and data-boundary tests.
5. Run related tests, integrity, CodeQL, domain boundaries, then full CI on the
   **final** SHA. Any edit invalidates previous acceptance.
6. Mark run status **PASS only with the matching evidence**; never promote a
   scoring estimate into measured quality. Review unresolved paths without
   assuming that every literal string is a real dependency.
7. A physical Lenovo release requires real dirty-worktree preservation receipts,
   successful runtime start/rollback, and measured Graphify if enabled. Keep
   deployment HOLD until then.

**Evidence-based evaluation**: use PASS/FAIL/HOLD for each gate, not a
fabricated 100-point quality score. The map deliberately returns
`quality_score: null` and `physical_device_verified: false` until a separate
instrumented evaluation exists. The plan is guidance, never authorization to
rewrite code, bypass gates or automatically merge the branch.

## Change acceptance gates
1. Record baseline commit, issue and test evidence; identify whether each artifact is tracked source, generated data, local-only customization or backup.
2. Specify failure reproduction and expected behavior before patching.
3. Change one bounded subsystem per PR; retain API and data schema compatibility unless explicitly migrated.
4. Add negative/hold tests, security checks, rollback path, performance budget and deterministic regression tests.
5. Verify manifest hashes and all required CI at exact PR head; avoid merging on stale checks.
6. Do not claim device PASS until Termux runtime receipts and post-update verification exist.
7. Preserve last-good and require explicit approval for risky local migration or deletion.

## Open decisions
- Obtain the exact device-local diff and backup receipt before any tablet-side update.
- Confirm whether a nonzero autonomy exit for V387 HOLD is intentional contract or scheduler reporting bug; do not guess.
- Build dependency coverage for JS, shell, and runtime-only artifacts incrementally; static import edges are not proof of runtime execution.
- Grade only evidence-backed coverage and tests; **do not assign fabricated 95/100 or 100/100 scores**.

## Iteration ledger template
| SHA | Subsystem | Reproduction | Fix | Unit | Integration | Security | Performance | Device | Decision |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 4c8e210 | Static Python code map | Repository smoke | Read-only map | 3/3 on PR | Repository smoke on PR | CodeQL on PR | Not measured | Not verified | Baseline only |

## Follow-up updater source review (2026-10-20)
- `ANDROID_UPDATE_AND_START.sh` lines 239-248 block updates without an update lock, on non-main branch, or with staged changes.
- Lines 319-340 classify unstaged dirty paths and refuse to update when modified source/configuration paths are present.
- Lines 359-405 preserve eligible runtime JSON and attempt restoration if fast-forward fails.
- **Residual risks to test, not presumed defects:** backup/restore failures, untracked path collisions, bootstrap-script normalization, state reporting when updater skips an update, and whether scheduled autonomy failure is an expected safe HOLD.
- Do not remove these existing protections or change device state while investigating.
