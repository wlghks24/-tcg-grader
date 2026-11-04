# V898 — unified view failure isolation and non-blocking photo loading

Base: `a29e5973d2824958467747a198b4d77d06f9464c`, PR #971.

## Evidence and limits

User-supplied device readback confirms matching working-copy/runtime SHA, healthy collection, and working events/feature-directory routes. Only unified_route is false. The V897 boolean-only result does **not** distinguish timeout, HTTP error, missing marker or corrupt state; it does not establish the exact device root cause.

Two source-level failure paths are confirmed/reproduced:

1. bridge source window is capped at1500; per-source input bounds reject more than10000 price rows. read_live calls strict unified_feed, which raises for source errors/truncation, and the prior unified-page route returns503 for the whole view.
2. live page used the self-contained export path: up to60 synchronous full-size codec trials before any HTML response, despite a5-second readback timeout. Cold-photo costs are device-dependent; no tablet performance improvement is claimed without measurement.

## Change

- New `tablet_live_view_v898` builds a read-only view. Explicit partial display validates row identities and refuses any supplied matches, returns objects flagged `display_only` / `SOURCE_COVERAGE_INCOMPLETE`, and does not invoke canonical project/reconcile. It shows the partial/error/window state in a banner. No files are deleted and no partial catalog becomes complete evidence.
- The default unified_feed and export paths **still reject incomplete reports**. Existing collector/reconcile/priority behavior is unchanged and remains fail-closed. This change does not expand the full catalog scan bounds or solve the deferred full-catalog reconciliation work.
- Complete view still performs the normal canonical read projection. Invalid catalog, feed or canonical state continues to fail with503; it is not silently replaced with an empty successful view or reset.
- Live HTML emits same-origin lazy image URLs instead of encoding/embedding photo bytes during page GET. Standalone exports retain their previous behavior/size limits. The image endpoint uses Host then loopback guard,32-hex ID validation, existing source-integrity checked bounded cached_display, valid image MIME and private/no-store headers. Original photos remain unchanged. No background worker/scheduler was added.
- Live CSP permits data plus self images; standalone remains data-only. Existing collection buttons, event routes, feature directory, filters and original zoom links remain.
- Diagnostic details now report HTTP status, MIME category, elapsed milliseconds, timeout/response failure, view data state and three allowlisted failure stages. Bodies/names/image IDs/exception text are not output. A partial view HTTP pass remains `HTTP_READBACK_OK_TOUCH_UNVERIFIED`, with PARTIAL_READ_ONLY explicitly reported; this is not complete data, learning success or camera/touch proof.
- Launcher now pins the new view module as part of its code check. Delivery tool remains unchanged: preserve private JSON, local main and original sources/Boot, normal guarded detach only.

## Validation

- Local Python3.12: **54 tests PASS** (15 new view/diagnostic tests plus39 existing V897 delivery/readback tests).
- Actual source_rows fixtures reproduce10001-price-row rejection and1501-source window cap; strict path still raises, explicit display keeps a bounded flagged/unlinked subset.
- Page fixture with100 photo rows proves no photo-byte read/codec call in page render; complete pair/canonical behavior and standalone CSP retained. Partial view creates no files and never calls project.
- Diagnostics cover HTTP503 vs direct/wrapped timeout, malformed/truncated responses, allowlisted stage extraction without private body leakage and partial data state staying explicit.
- New actual handler image-response test is registered in the existing full CI suite; not run locally because the restored workspace lacks its full image-auto/metadata fixture dependencies. Do not describe local tests as complete runtime/device validation.
- Independent source review and initial12 mock tests found no new blocker; reviewer correctly reported the endpoint fixture as unavailable locally. Existing source/default validation and privacy/Host/loopback rules remain.
- Compilation/Bash syntax/manifest byte pins/whitespace checks executed. Code Preflight selected-source scope is separate from full repository CI. Main remains unchanged; no device command executed by the agent.

## Device follow-up after current-head CI

Use the existing pinned V897 delivery tool with the observed a29... base and the new reviewed commit. Re-run device readback. The new details distinguish HTTP errors/timeouts and state-related failure stages; PARTIAL_READ_ONLY still requires catalog coverage recovery. Touch/camera, actual image/event collection receipts, persistent Boot and main release remain outstanding until separately verified. Do not mark the whole tablet finished merely because new-route HTTP checks pass.
