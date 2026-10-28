# W401–W500: selected source/test evidence review (partial, not 100 versions)

- Review date: 2026-10-28 KST
- Protected original main: `6c78831bbb6e188717f86ef90243a836d2e0b67a`
- Prior evidence chain: parent PR #905, finding ledger `execution/evidence/version_review_findings_v001_v879.json` (17 scoped findings, no whole-version score)
- Read-only analyzer: `execution/historical_v401_v500_forensics.py` and its deterministic tests
- **Honesty gate:** source/test Git blobs and assertions verified ≠ runtime exercise, all-feature audit, visual QA, data-provider verification, or Lenovo receipt.

| Version | Pinned evidence scope | What a result actually supports | Remaining evaluation |
|---|---|---|---|
| V413 | `test_promoted_tcg_source_monitor_v413.py`, monitor source | Catalog/rarity parsing, mocked source collection and fail-closed partial failure; monitor has disk evidence-writing path | Live source provenance, collection freshness, error retry and receipt must be separately tested |
| V426 | exact sync contract, receipt and `test_tablet_gpt_tcg_grader_sync_v426.py` | Exact watched grading prefix, candidate successor/history claim, stored digest/lesson controls; receipt explicitly `physical_tablet_runtime_verified=false` | No automatic runtime release; any new `grading_` edit must use reviewed successor |
| V430 | `test_tablet_category_focus_v430.py` | Source-expression checks for hiding detail panels, back/collapse controls | Real rendered browser click/viewport/console, back navigation and physical touch test |
| V437 | `tcg_discovery_inbox_v437.py`, `test_tcg_discovery_inbox_v437.py` | Bounded WATCH-only discovery, test URL `https://official.example/game`, https/hostname shape | No actual official URL ownership/live evidence demonstrated; WATCH must never auto-enable grading |
| V468 | `test_main_tablet_only_learning_v468.py`, protected `main` and schedule SHA | Existing local-only CLI and scheduler string-contract assertions | Actual Termux command execution, storage limits, trained-model output and device readback not demonstrated |
| V485 | `test_tcg_market_home_v485.py` | Static HTML/JS source contract, saved JSON, optional Node.js syntax | No screenshot-derived browser rendering verified; complete interactive UI/performance not certified |
| V489 | `test_grade_context_purchase_v489.py` | Exact card/game/edition identity via 16 local Node.js examples and source-contract assertions | Not actual purchase, real shop availability, or card lookup accuracy |

## Findings to carry forward
- **W401-F001 (existing P0):** V426 watched path successor is mandatory for changed grading source; retain the original finding unchanged.
- **W401-F002 (P1, TEST COVERAGE GAP):** V413 mock-based signals are insufficient as proof of production provider availability or freshness. No new production bug claimed.
- **W401-F003 (P1, DEVICE/UX EVIDENCE GAP):** V430 static expressions do not prove all tablet menu interactions.
- **W401-F004 (P1, PROVENANCE GAP):** V437 `official.example` fixture exercises shape, not actual official host validation. WATCH is safe but promotion remains review-gated.
- **W401-F005 (P1, TERMUX EVIDENCE GAP):** V468 local-only test checks commands in source, not execution on Lenovo.
- **W401-F006 (P1, VISUAL QA EVIDENCE GAP):** V485 source/Node checks do not prove a screenshot-matched visual layout or responsiveness.
- **W401-F007 (P1, INTEGRATION GAP):** V489 local Node harness is not independent provider/customer purchasing verification.
- **W401-F008 (P1, DOCUMENTATION/QUALITY GAP):** These seven historical *selected tests* cannot be scored as 100 completed versions, and there is no fair 0–100 score without whole-function review and real behavior evidence.

All quality values remain `null / NOT_RATED`; physical tablet verified=false. Historical PR #905 and its 17 findings remain an unmodified ancestor. A successor or production patch is proposed only after reproducing a concrete behavior flaw against current source and considering protected history. **No main merge / no Lenovo install** from this review.
