# TCG AI_UPLOAD 2026-10-29 — read-only review and prioritized patch handoff

Status: **DRAFT / HOLD**. This is an evidence and PC reviewer patch intake; it is **not** a claim that the TCG runtime or all static candidates have been fixed.

## Source/evidence alignment
- Upload: `AI_UPLOAD.zip`, SHA-256 `b8b2bc3171153afb5937e43ae972ae6b07341c6b3b6396aa9a14bb3572924df7`.
- Manifest: 4 payload files individually match declared byte lengths and SHA-256; `snapshot_sha256_by_file` exactly matches `review.original_sha256`.
- Report: 1,835 scanned files / 18,308,853 scanned bytes; 90 skipped entries, mostly non-Python/JSON. No automatic source patch applied; no optional project test run; Ruff NOT_REQUESTED.
- Local Git `HEAD = 6c78831bbb6e188717f86ef90243a836d2e0b67a`, which was independently confirmed as GitHub main HEAD on 2026-10-29. **This does not prove a clean worktree or that each local file equals GitHub content**.
- `original_unchanged_during_scan: true` establishes intra-scan stability only.
- Git branch inventory: only local remote-tracking references, `remote_freshness=NOT_FETCHED`, first 100 non-merged refs, `truncated=true`; these are not confirmed unimplemented features or PRs.

## Static findings triage
| Type | Count | Interpretation |
| --- | ---: | --- |
| Architecture repair candidates | 1,504 | ALL P2 / NEEDS_REPRODUCTION_AND_REVIEW, not confirmed bugs |
| Complexity heuristics | 1,235 | No behavioral failure shown |
| Duplicate body groups | 269 | AST body equality only; signatures, bindings, behavior and consumers not checked |
| Duplicate file groups | 56 | May include policy docs, tests and historical fixtures; not safe to delete |
| Format-only observations | 70 | End-of-file newline; not functional defects |
| Intentional no-op/stubs | 6 | Verified samples include Protocol signatures, HTTP log suppression and test doubles |
| Auto-applied patches | 0 | Correct safe HOLD |
| Project functional tests | NOT_RUN | No production runtime certification |

**Do not auto-remove files** from duplicate groups such as `AGENTS.md / CLAUDE.md / GEMINI.md`, and do not treat a local ref count as a missing-feature count.

## Reproduced defects in the PC reviewer package (not TCG runtime)
Review source: standalone `TCG_PC_Reviewer_v0.11.2_ChatGPT_Upload_Watch_Windows.zip`; SHA-256 `c4a225fbad408a3794dc6223bea8cf9deee8104fbcb9def8dd67f10474ed36d1`.

1. `source_watch.differences`: with 41 added files and `limit=40`, the output list has 40 items but `truncated=false`; fixed by checking per-group length.
2. `upload_bundle.build_bundle`: `Path.resolve()` before `is_symlink()` masks whether the original report path is a symlink; fixed by checking the supplied path first.
3. `INSTALL_GLOBAL.cmd` referenced v0.11.1, while the current package installs v0.11.2; v0.11.3 uses a separate v0.11.3 directory and consistent display strings.

Standalone v0.11.3 archive SHA-256: `edd355354ee0fcf48d3142b365b5b29d7f3e37491971ab31f8bd4be397bcbbb9`. **The standalone ZIP is supplied in the user conversation, not committed as binary here**.

Local verification of standalone v0.11.3 package: **77 unittest PASS**, preflight PASS (24 Python sources, 39 manifest-listed files), ZIP CRC PASS. Windows GUI, full TCG functional/runtime regression, PR GitHub CI, and Lenovo physical device remain UNVERIFIED.

## Backlog priority / next patches
1. P0: Confirm manifest/CI integrity for this PR at current HEAD; no protected main write.
2. P1: Obtain concrete source and reproduce any syntax/data loss/security/functional defect before changing runtime behavior. None confirmed by this upload.
3. P2: Prioritize true cross-component candidates by actual caller/dependency and protected-contract scope, verify with targeted tests; distinguish historical patch scripts, fixtures and versioned tests from active runtime.
4. P2: Improve AI handoff selection: current request includes only the **first 30** of 1,504 alphabetically ordered tasks; it is not a risk-ranked list.
5. P3: Non-functional newline observations are deferred where protected hash churn would require successor verification.

**Required checks before merge**: exact source SHA check, matching live file SHA per target, reproduction test, minimal diff, targeted regression, CodeQL, integrity manifest, SELFREFINE/Sync tests, latest-HEAD CI, and explicit release decision. No automatic merge, GitHub remote pull into PC, or Lenovo installation.
