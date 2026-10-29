# TCG PC Reviewer v0.11.2 — ChatGPT handoff and read-only local watch (review-only)

## Scope
This document records the local PC ZIP verification and the proposed handoff workflow. **The v0.11.2 binary/source ZIP is not stored in this PR**. The current PR #921 contains an earlier auditor, not a verified v0.11.2 installation package.

Local package SHA-256 (generated from the uploaded v0.11.1 ZIP): `c4a225fbad408a3794dc6223bea8cf9deee8104fbcb9def8dd67f10474ed36d1`.

Local development verification: 75 Python unittest cases PASS; preflight static import/integrity PASS; ZIP CRC PASS; uploaded report-bundle reconciliation PASS against a synthetic fixture. Windows GUI, full TCG history, GitHub CI for v0.11.2, and Lenovo device remain UNVERIFIED.

## Offline workflow
1. On Windows, choose the complete local TCG source directory; report output must be outside the repository.
2. The v0.11.2 local watcher polls the PC source tree at ~3 seconds using metadata, then debounces changes ~2 seconds before scheduling a new read-only local scan in a separate report folder.
3. After local review, it creates `AI_UPLOAD.zip` containing `review.json`, `architecture.json`, an AI task request, file SHA-256 digests, and support reports. Source code and credentials are not deliberately bundled; inspect files before sending.
4. The user attaches the ZIP in ChatGPT. ChatGPT independently verifies findings, obtains actual source from the repository at a matching commit, reproduces defects where possible, and proposes minimal source+test patches on a new development branch.
5. Run CodeQL, integrity, security, regression and required GitHub checks before any merge. Do not auto-merge or deploy to Lenovo.

## Critical caveats
- Local file-watch does NOT synchronize remote GitHub commits to the PC. No unattended `git fetch`, `git pull`, commit, merge, source overwrite or model API calls.
- Current local scan is STATIC EVIDENCE. It does not certify all historical versions or functional behavior.
- The GitHub PR's source revision must match reported file hashes before patching; otherwise HOLD/RE-SCAN.
- Retain the previous auditor and original source unchanged until the new version passes independent Windows and CI validation.

## Patch sequence upon evidence upload
P0 security/integrity -> P1 reproduced defects/unimplemented functions -> P2 duplication and module dependency simplification -> P3 formatting. Every fix requires: evidence, reproduction, affected paths, minimal diff, tests, regression, CI receipt, and unresolved risks.
