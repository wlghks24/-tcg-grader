# V637 top-level file organization — Stage 1 (2026-10-14)

## Purpose and safety boundary

GitHub's root directory display truncates beyond 1,000 entries. At the reviewed
main SHA `c452e73c0ca48132b560a815819b054066abaf6f`, the **full non-truncated
Git tree** had 1,018 root files plus 19 directories (1,037 root entries), so
GitHub omitted 37 entries **from the UI only**. No tracked file was deleted by
the GitHub display warning.

This first stage archives historical **text-only, no-indexed-code-reference**
material. Every relocation was performed by (1) reading the original file at
the V637 branch, (2) writing the exact same UTF-8 text to the archive, (3)
fetching and confirming that the source/destination **Git blob SHA and text
were identical**, and only then (4) deleting the redundant root path.
No executable code, protected manifests, active candidate data, packaging or
Lenovo synchronization contracts were relocated.

## Historical documents relocated

| Previous root path | New archive folder |
| --- | --- |
| `CARD_IDENTITY_LEARNING_RESULT_2026-08-28.md` | `research/` |
| `DAILY_0600_COLLECTION_INSTAGRAM_AUDIT.md` | `reports/` |
| `PERFORMANCE_REVIEW_V258.md` | `reports/` |
| `TCG_BOX_DATA_COVERAGE_V623.md` | `research/` |
| `TCG_OFFICIAL_PRODUCT_EVIDENCE_V627.md` | `research/` |
| `TCG_GRADER_AI_RELIABILITY_V8_OPERATING_PRINCIPLES.md` | `research/` |
| `TCG_FREE_120_POINT_SCORECARD_V621.md` | `research/` |
| `TCG_GRADER_100_1000_HANDOVER_V332.md` | `reports/` |
| `TCG_USER_30_GAME_RESEARCH_V625.md` | `research/` |
| `SELFREFINE_COLLECTOR_ISOLATION.md` | `reports/` |
| `V136_NOTES.txt` | `legacy-notes/` |
| `V136_RUN.txt` | `legacy-notes/` |
| `V136_VERIFY_MARKERS.txt` | `legacy-notes/` |

Each destination is relative to `docs/archive/`.

## What was intentionally NOT moved

- `FINAL_VERIFICATION_REPORT.json`, `INTEGRATION_REPORT.json`, `V109_FINAL_VERIFICATION_REPORT.json`,
  and other V100+ reports: runtime/verifier modules refer to exact root paths.
- `GPT_DATA_ENGINE_GUIDE.md`, `GRAPHIFY_CHATGPT_GUIDE.md`,
  `TABLET_COLLECTION_PUBLISH.md`, `TABLET_GDRIVE_SYNC.md`,
  `WORKFLOW_PUBLISH_SAFETY_V363.md` and the V482/V483 external-app reviews:
  active CI/workflow or crosscheck contracts reference these paths.
- All root `test_*.py`, `apply_*.py`, runtime CSS/JS, static market data,
  Android/Termux scripts, `integrity_manifest.json`, and protected source
  registries: some are executed/imported dynamically, hashed, or distributed
  to tablets. Moving them requires explicit dependency remapping, exact-head
  CI, historical snapshot checks, and device readback.

## Follow-up quality gates

1. Compare the root directory entry count before/after; note that adding the
   new `docs` directory also counts as one new root entry.
2. Review the PR diff: 13 original files should appear as rename/copy+delete,
   with **no altered file contents**. Verify the full tree is not truncated.
3. Require repository integrity, Main/Deep/Exhaustive SELFREFINE, CodeQL,
   and 400-case Tablet GPT Main Alignment PASS for exact PR head SHA.
4. **Do not merge** on partial CI. Preserve protected main and device last-good.
5. Treat root-entry reduction below 1,000 as a separate later milestone; no
   unverified bulk moves merely to suppress a cosmetic GitHub warning.

## Long-term root budget policy (V638)

The Repository Integrity Guard now runs a standard-library-only root entry
check on each PR and `main` push, comparing with the exact PR base or
pinned previous main commit respectively. Manual runs check the hard cap.
The checked-out Git tree, **not GitHub's
truncated web view**, is authoritative.

- Stage-1 baseline and temporary hard cap: **1,025** root entries after PR #669.
  This is intentionally not presented as a fix to the web-listing warning.
- **Monotonic rule:** any PR adding root entries must also remove enough
  verified root entries to keep its merged tree's root count **at or below the
  pinned base commit's count**. A move that adds one new top-level directory
  uses one root entry too.
- Once the root count drops below **1,000**, an ordinary PR cannot raise it
  again. Root targets are **<=900** as an initial headroom milestone and
  **800–900** as a sustainable working band, subject to exhaustive path
  compatibility and tablet readback.
- Put new tests under `tests/`, migration scripts under `scripts/`, and
  research/reports under `docs/` when all imports, workflows, hashes, and
  packaging are already compatible. Do **not** auto-move operational
  entrypoints, market data, CSS/JS bundles, or files referenced in historical
  integrity/provenance fixtures.
- A genuine new root launcher is allowed only if the same reviewed PR
  safely archives another redundant root entry. The PR is blocked if the
  total root count grows. No temporary blind deletion to pass the gate.
- This policy prevents regression, **not** the initial 25-entry cleanup.
  Further refactors are separate small PRs with full 400-case tablet,
  CodeQL, integrity, SELFREFINE, and runtime CI verification. The original
  exact-content archive mapping above remains the restore plan.

To roll back an archive relocation, use the identical Git blob at its new
location and restore the old path via a reviewed PR. Never overwrite a device
or historical provenance snapshot based on a UI-only directory warning.
