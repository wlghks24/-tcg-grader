# v0.11.6 — fix two-pass global upload incompatibility (Draft/HOLD)

## Reproduced from uploaded report
The submitted `GLOBAL_AI_UPLOAD(1).zip` was integrity-valid, but included only `pass_1/` reports. `double_review_receipt.json` claimed two matching passes, while the local `report_inspector.inspect_archive()` explicitly requires **both** `pass_1/` and `pass_2/`. This caused a legitimate self-generated bundle to be rejected as `missing_double_pass_file`.

## Tested standalone fix
The downloadable Windows `TCG_PC_Reviewer_v0.11.6_Double_Pass_Verified_Windows.zip` (SHA-256 `97b1a73a0546c6a6154936e0824188e38c8330fab52510c259690fa114f87cf9`) updates `global_upload.py` to include both pass reports, preserving 7/7 SHA-256 equality checks and 55MB total cap. A new integration test creates a temporary Git repo, runs both scans, packages the ZIP, and checks it with `report_inspector`.

- Standalone ZIP re-extraction preflight: PASS (29 Python files, 47 manifest-listed package files).
- Standalone full unittest: **88/88 PASS**.
- v0.11.5→v0.11.6 core source/test unified patch: `docs/pc_review/TCG_PC_v0115_to_v0116_Standalone_CoreFix.patch.zlib.b64`, decompressed patch SHA-256 `d3308e00016b58f7f4c3e51a4f10d0353cb9cc7fa4d3ff0647e0ad590002c973`; locally `git apply --check` PASS and applied bytes matched v0.11.6 source.
- Decode: Python `Path('patch.diff').write_bytes(zlib.decompress(base64.b64decode(Path('TCG_PC_v0115_to_v0116_Standalone_CoreFix.patch.zlib.b64').read_bytes())))` after importing `base64,zlib` and `Path`.
- These patch bytes cover the core module and regression tests, **not the full Windows installer**. The standalone ZIP remains the distribution artifact and is not in GitHub.

## Operating limitations
The previous submitted GLOBAL ZIP contains no pass_2 bytes. Do **not** fabricate the second pass; rerun the global two-pass scan in v0.11.6 to obtain independently verifiable evidence. User's local `AI_UPLOAD.zip` can be kept. This does not validate 11,373 historical commits functionally, and none of the 214 static leads becomes a proven defect automatically.

Windows GUI hands-on and Lenovo physical testing are NOT VERIFIED. No main merge, no auto-repair, no GitHub automatic fetch/pull, no Lenovo install. Keep Draft/HOLD until GitHub CI and device gates.
