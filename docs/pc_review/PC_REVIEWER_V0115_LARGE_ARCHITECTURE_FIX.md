# PC Reviewer v0.11.5 — recovered large architecture upload evidence

Status: **DRAFT / HOLD**. This is a read-only PC reviewer release note, not a TCG runtime code change.

## Trigger reproduced
2026-10-30 Windows screenshot: current-source static review completed and `AI_UPLOAD.zip` failed with `report_bundle_size_limit:architecture.json`.

Root cause: standalone v0.11.4 `upload_bundle.py` rejected a single report entry larger than 12,000,000 bytes, even when the data was a valid JSON architecture map. It had no UI action to create the handoff ZIP from an already-written report without rerunning the scan.

## Standalone v0.11.5 solution
- Deliverable `TCG_PC_Reviewer_v0.11.5_Large_Report_Recovery_Windows.zip` — SHA-256 `24fa151eb2b870877a0ffdece792960ade8a1a90f19ab8d97a79409225647c5b`.
- Add bounded compact JSON packing for oversized `architecture.json`. For still-oversized JSON, use a bounded `architecture.json.gz` payload, with `UPLOAD_MANIFEST.json.transformed_reports` recording source and transformed payload digest/size/encoding.
- Preserve original report bytes, all task records and original source code.
- Add read-only `기존 검사 결과에서 AI_UPLOAD.zip 복구` GUI action to rebuild a handoff ZIP from an existing report folder without rescanning source.
- Update ZIP inspector to recognize compressed JSON architecture and validate the compressed-file hash with bounded decompression (64MB cap).
- Lift the standalone AI handoff JSON parsing limit from 10MB to 64MB, retaining HOLD on oversized/unsafe input.
- No automatic GitHub pull, source overwrite, AI submission, auto-merge, or Lenovo install.

## Local evidence
- Independent package extraction: 29 Python sources compile/import preflight, 46 SHA256-manifest-listed files, **87/87 unittest PASS**.
- Real previously submitted `AI_UPLOAD.zip` architecture (11,607,440 bytes), padded to 12,000,001 bytes without changing its parsed JSON value: successfully generated AI_UPLOAD.zip; the crosscheck reconstructed 1,006 modules, 9,289 functions, 269 duplicate-body groups, 56 byte-identical file groups, and all 1,504 tasks. Source report remained unmodified.
- Synthetic JSON larger than 12MB **after** minifying: lossless gzip upload and inspector acceptance.
- Tampered compressed digest, excessive original architecture report size, and existing ZIP overwrite fail closed.

## Important boundaries
This repository PR contains **release evidence only**. The exact full standalone v0.11.5 ZIP and v0.11.4→v0.11.5 patch are currently delivered as ChatGPT artifacts rather than registered as native GitHub source files. **GitHub CI on this documentation commit cannot certify the standalone Windows release.** Windows GUI manual execution and real TCG functional regression are NOT VERIFIED.

Remain Draft/HOLD, main protected. No runtime source modification.
