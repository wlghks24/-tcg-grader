# V701–V800: Historical original provenance investigation (HOLD)

**Protected main SHA:** 6c78831bbb6e188717f86ef90243a836d2e0b67a. **Parent candidate:** PR #912, with 38 previously carried scoped findings. **Current status:** provenance not established; no numeric version quality scores or Lenovo approval.

## Why earlier zero hits cannot be called a completed review
The existing V1–V879 evidence matrix reads tracked file paths and the FIRST LINE of reachable commit messages. It found no V701–V800 path/commit-title markers in protected main. A separate search of 869 PR title/head branch/body-summary fields also reported zero strict V7xx matches. Neither proves all 100 versions were never created; a release could be hidden in the body of a commit, annotated tag, other ref, archived source or physical device.

## Expanded local Git-only scan
The independent scanner checks exactly the protected-main original commit ancestry:
- Count all original commits reachable from the protected main SHA. Reject shallow/incomplete history and refuse to claim a complete review if the scan is capped.
- Search entire Git commit messages (not just first-line subjects) with strict standalone V701–V800 tokens, rejecting dates/embedded sequences.
- Search fetched local Git tags and origin remote-ref names separately. Each hit is classified as metadata lead, never a proven release or test.
- Do not download untrusted scripts, run historical runtime, modify old manifests, write to source, or set quality score/device flags.
- Keep the source/branch search result distinct from separate GitHub PR-only history; a clone's fetched refs may be incomplete even when its local Git main ancestry is complete.

Any match must be followed by an original Git object, file diff, active source/test contract, and version-specific regression before status can progress beyond PROVENANCE_LEADS_ONLY_REVIEW_REQUIRED.

## Findings inherited
Parent #910 W501 scope carried 31 findings; parent #912 W601 scope carried **38** including seven new evidence gaps. This W701 scan does not erase or supersede those findings, does not create synthetic V701–V800 versions, and does not give an invented 100/100 score. The 100-slot region remains NOT_AUDITED until independent original source evidence is found and analyzed. Status remains **NO PHYSICAL TABLET RECEIPT / HOLD**.

**Next W801–V879:** review the open V879 draft PR #896 as an integration candidate and the V878 dock successor proof independently; 22 CI checks success is not physical Lenovo UX or approved installation.

## Newly recovered V732 historical source edge (2026-10-28)
The expanded 6,613-commit original-main *full-message* scan found **one standalone V7xx token**: V732 in landed commit 0a22abfe02cd8931227e63562d417795932063fd. The token was in the commit BODY, not the filename or first-line subject. The original commit message identifies a fix for nine CSS-fragment titles in card event candidates (PR #732), plus a specific pinned CSS-only source successor.

Concrete immutable Git objects:
- Baseline event data commit 82f1220dc9137ef5a30f41ad5cbd9fb7e7335eae / Git blob 00ce8c41398bde6588171b1822e89a6c32fb8996.
- V732 landed commit 0a22abfe02cd8931227e63562d417795932063fd / updated event data blob 813f6d79a375bdee80fcd1959eed0989a1202920.
- Current protected-main sync source blob 6b899d70c835253f8381ffb0e6fb8740a413951f includes an explicit V732 exact-landed-commit and source-byte gate within the V545/V565 lineage, not an unrestricted V732 exception.

A separate original-Git forensic test now compares parsed event data before/after, checks exactly nine removed CSS-looking title rows and preserved semantic data, original three-path change scope, immutable guard and tamper rejection. Even if all checks pass, this is **evidence of one reviewed historical DATA FIX**, not proof V732 was a production release, and not a 100/100 review of V701–V800 or physical Lenovo delivery. Leave other V7xx numeric slots as unreviewed pending exact original evidence.
