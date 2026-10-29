# PC Reviewer v0.11.4 — offline evidence workflow release checkpoint

**Status: DRAFT / HOLD; no source patch to TCG runtime or protected main.**

## Standalone Windows package

- File delivered in the ChatGPT conversation: `TCG_PC_Reviewer_v0.11.4_Priority_GitHub_Handoff_Windows.zip`
- SHA-256: `7df9a78d95298d7f7b4ea988a3f7692f292a3c035bed331fdae95e46fff27a92`
- Full standalone source (including Windows launcher, SHA256 manifest, and tests) is in that local ZIP, **NOT yet imported into this GitHub branch**.
- Independent ZIP extraction: 28 Python source parse/compile, 44 manifest-listed package files, 83/83 tests PASS, ZIP CRC PASS; Windows GUI physical run NOT VERIFIED.

## Meaningful improvements over v0.11.3

1. `PRIORITIZED_BACKLOG.json`: preserve all 1,504 static triage leads, now ordered by severity, import impact, rule and protected-path review risk. None is automatically called a confirmed defect.
2. `AI_REVIEW_REQUEST.json`: diverse 30-file/task handoff (actual user case: 15 duplicate-body and 15 complex-function leads across 22 file paths); the full backlog is included in `AI_UPLOAD.zip`.
3. `VALIDATION_EVIDENCE.json`: explicit statuses for Ruff, optional unit tests, Windows/Lenovo, remote GitHub and latest-head CI. Cannot mark missing checks PASS.
4. `GLOBAL_AI_UPLOAD.zip`: after offline global scan, only created when the two independent reports match file-level SHA-256/byte receipts. Includes global history/version hints and code-map summaries, no original source.
5. Optional manual GitHub public `main` SHA and first-page public open PR metadata check, **read-only**. No source, secrets or local report sent. Public GitHub API may be unavailable/rate-limited; failure is HOLD, never zero PRs.
6. AST duplicate candidates now expose signature/decorator/async/scope compatibility hints. Matching AST body is never proof of semantic equivalence.
7. Existing 3-second local watch remains separate from remote sync: no `git fetch`/`git pull`, no model dependency, no automated source edit/merge.

## Reproducible evidence

- Re-evaluated uploaded `AI_UPLOAD.zip` with 1,504 tasks, 1,835 source hash entries. 1,504 of 1,504 preserved in complete backlog; no P0/P1 findings in this particular static report.
- Locally generated and tested standalone v0.11.3 → v0.11.4 source patch: `TCG_PC_v0113_to_v0114_APPLICABLE.patch`, SHA-256 `f73d5fe8883eeb0a8c1b12943ac15ff4d3ada30898a98127bab7e78bd50d3b9b`. **Patch bytes are in the ChatGPT artifact environment, not yet uploaded to this GitHub branch.** Applied to clean v0.11.3 extraction and reran 83/83 PASS; no GitHub CI for the full new code package yet.

## Corrected v0.11.2 → v0.11.3 patch

The original incomplete `TCG_PC_Reviewer_v0113_CoreFixes.patch` did not apply with plain `git apply`. It has been removed from this PR. Its replacement `TCG_PC_v0112_to_v0113_verified.patch.zlib.b64` is the *actual unified patch* compressed with zlib and encoded as base64 to avoid repository whitespace-check false alarms.

To decode in a trusted Python 3.10+ terminal from the `docs/pc_review` directory:

```python
import base64, zlib
from pathlib import Path
p = Path('TCG_PC_v0112_to_v0113_verified.patch.zlib.b64')
Path('TCG_PC_v0112_to_v0113_verified.patch').write_bytes(zlib.decompress(base64.b64decode(p.read_bytes())))
```

Decoded patch SHA-256: `027892a7a6da9d52c9b54b4c63bdb5473fbcc7811bf186bc1217cccee9ecda4b`. Locally tested `git apply --check` on clean standalone v0.11.2 package. Do not apply this patch to the older GitHub `tools/pc_version_auditor` implementation because it is a different source layout.

## Release gates

Protected `main` unchanged. This PR remains **Draft/HOLD** until the v0.11.4 source is imported into a suitably isolated branch, GitHub CI validates **that actual source**, optional real Windows GUI tests are collected, and functional TCG candidate fixes are individually reproduced. None of the 1,504 candidates has been auto-fixed by the reviewer.
