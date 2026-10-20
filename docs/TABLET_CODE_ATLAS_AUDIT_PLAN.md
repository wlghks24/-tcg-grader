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
