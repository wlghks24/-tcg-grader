# PR #953 follow-up audit — evidence and open gates

## Verified on GitHub
- Exact PR head `0bae68916ddb50a2a4aaac28522f4a2bbdd93d0d`: ten PR workflows reported success, including repository integrity, Deep SELFREFINE and CodeQL.
- The prior integrity failure was missing manifest entries for the two new tracked Python files; both were registered without weakening the guard.
- The existing `index.html` front/back preview images and `manual_dual_photo_bridge.js` preview image have alt text in inspected excerpts.
- Existing tablet UI skill instructions already cover tablet viewport, touch targets, accessibility, loading/error states.

## Accuracy limitations found
1. `image_alt_review` only tests whether the whole HTML file contains any `alt=`. It can miss an image lacking alt when another image has alt; also comments and JavaScript strings can create false positives. Replace with a per-element HTML parser and targeted tests before using as a quality gate.
2. Structural AST equality can flag behaviorally different functions due to scope/decorators or contextual dependencies. Findings are review candidates, never deletion authority.
3. `rglob` scans a bounded file count but does not impose a global traversal time/entry budget; large repositories require performance measurement.
4. No GitHub Actions step currently proves the new dedicated `test_external_skill_review.py` was run. General CI success is not a substitute.
5. Full repository scan JSON and actual Lenovo screenshots/receipts are not yet available.

## Next safe execution
- Run `python -m unittest execution/tests/test_external_skill_review.py -v` on the exact PR checkout.
- Run `python execution/external_skill_review.py . --max-files 1500 > /tmp/tcg_external_skill_review.json` in read-only mode.
- Preserve JSON artifact and annotate each candidate with path, line, reproduction and severity; compare with existing code map.
- Improve parser/test accuracy in a separately verified commit, updating `integrity_manifest.json` with exact bytes and SHA256.
- Re-run all required CI on that exact head. No auto-fix, merge or tablet deployment until release gates and physical verification.

## Verification honesty
The GitHub CI success is confirmed. A separate local prototype with three analogous tests passed, but this was **not** execution of the exact PR file or a full-repository scan and cannot be counted as the repository's own test evidence.
