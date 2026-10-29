# TCG PC Auto Auditor v0.6 — GitHub source (review-only)

This directory contains the **exact 25 UTF-8 files** from the verified ZIP archive, without executing the source or modifying the TCG runtime. Full original archive SHA-256: `50966ad7d9064187a6c14f643d0664d7e57b8ff986a9cf7446448e7e5d0a5437`.

## Local testing

- Python 3.10+ and Git, standard library only for the default auditor.
- From this directory: `python -m unittest discover -s tests -v`.
- Windows GUI: run `실행_PC.bat`. Read `PC_사용설명서.md` before use.
- Use a *separate complete local TCG Git clone* as the input and keep output **outside** the repository.

## Mandatory safety contract

The program scans 100-number windows but does **not** certify that every number is a released version. Missing historical source, unresolved P0/P1/P2 issues, absent real semantic/regression tests or unverified devices **must HOLD** the next window. Double-pass report equality proves consistency only, not software correctness.

No unattended merge into protected main, no original-code rewriting, no Lenovo installation, no stock or vehicle project access. Registered local skills are review criteria, not trusted executables. Optional Docker/manual Windows schedule require separate operator action and validation.

## Readiness

**Source uploaded for DRAFT review, not production-validated**. Historical tests: 60/60 passing on temporary synthetic Git repos in the previous local environment. Full real TCG checkout, Windows GUI/scheduler, optional Docker and physical Lenovo tests remain **NOT VERIFIED**. Review GitHub checks on this PR head before allowing merge; no device permission implied.

See `검증결과.md`, `이중전체검수_운영규칙.md`, `SHA256SUMS.json`.
