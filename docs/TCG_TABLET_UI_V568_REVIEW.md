# V568 | Tablet UI clarity review

## Scope (2026-10-15)
Source: user-provided 56-second Lenovo tablet recording, reviewed privately. Do **not** upload original recording, frame captures, personal inventory photos, local caches, or graded photo data to public GitHub.

### Observed issues
- Multi-section home requires long scrolling; category navigator exists but several legacy support panels still appear in the general reading flow.
- The V485 market card / BOX list uses horizontal scroll strips; partially-visible tiles look clipped.
- Important titles, condition/printing/country filters and source status compete with small technical copy.
- Image-missing placeholders should remain honest. No invented item image, verified deal, completed sale or stock status.

### Change on this branch
Only `feature_category_nav.css`: larger responsive main layout, readable headings, compact category cards, two-to-four-column **full grid** for card/BOX listings instead of partial horizontal strips, larger touch targets, clearer dashboard typography. CSS-only; grading, evidence aggregation, identity resolution, data source, localStorage, API paths and market safety gates are unchanged.

### Deterministic preflight performed
- Verified existing CSS blob SHA and original V485 card/BOX selectors.
- Checked extension is CSS-only, balanced braces, no script/url/import, 2-column fallback and initial 44px market-card action targets, later raised to 48px under QA3.
- Tested a separate, **non-production** interactive HTML UI prototype with Playwright at 430px/800px: no horizontal document overflow; category and 5-tab routing, card/BOX filter, favorite save, local image preview, and store-list interactions exercised without JavaScript errors.
- The standalone prototype and these tests do **not** constitute a true integrated app test.

### Merge / deployment HOLD checklist
- [ ] Existing tablet navigation / market / grading regression suite passes against **exact PR head**, not an older SHA.
- [ ] Inspect actual app (not standalone prototype) at 320/360/390/430/600/800/1024/1280 CSS px for overlap, long Korean labels, grid overflow, hidden panels, bottom dock, focus and reduced motion.
- [ ] Verify service worker cache/update behavior after changed CSS; stale cached UI must not be called an update success.
- [ ] Validate category -> feature -> back and home-reset, and all existing legacy tools remain reachable.
- [ ] Preserve WATCH/promoted/grade gates, completed-sale vs listing tiers, variant-specific pricing, and image provenance.
- [ ] On Lenovo real device confirm touchscreen, portrait/landscape and scroll behavior and capture before/after evidence privately.
- [ ] Resolve prior v470/v471 navigation orphan-panel issue in a separate, reviewed runtime JS + successor-sync change; not silently in this CSS-only PR.

**Status:** DRAFT/HOLD. No claim of device installation, completed integration test, live market result, or production approval.


## QA2 / QA3 second-pass corrections (2026-10-15)

Standalone Chromium demo: small market-card buttons measured 39px high and ~60–87px wide at 320–430px. Updated demo buttons and branch visual rules to target 48px minimum, with full-width stacked actions on narrow tiles. Rechecked eight viewport widths (320/360/390/430/600/800/1024/1280), product navigation, country filter, BOX selection, favorites, photo preview, horizontal overflow and JS exceptions. This does not substitute for real-app or Lenovo device tests.

Production CSS: market sections are full width at >=800px, actions stack at <=430px, and market/shortcut/refresh controls have at least 48px minimum height. The existing V533 dynamic styles independently target 48px; visual regression must confirm the two layers coexist.

New gaps found, intentionally outside the CSS-only change:
1. P0: feature_category_nav.js hides allowlisted managed surfaces, but other legacy sections may still remain on long pages. Fixing orphan panels requires careful navigation/visibility + watched-sync tests; do not hide all sections indiscriminately.
2. P1: tcg_local_collection_v505.js production schema and region form currently support KR, JP, US only. The separate demo shows CN-S/CN-T conceptually; importing/storing simplified and traditional Chinese portfolio records is NOT yet supported. Introduce separate variant codes with migration/export/import and exact-grade/market tests.
3. P1: missing media should be treated as unresolved source evidence; verified pictures or local user-selected pictures may be shown according to rights/privacy. Do not upload private media to GitHub.
4. P1: touch target styling alone is not proof of actual 48dp on Lenovo; validate real device focus, accessibility scan, zoom, landscape and screen reader.
5. P1: index.html still requests feature_category_nav.css?v=485 and sw.js supplies network-first assets plus cache fallback. Test live/offline refresh and rollback; CSS on PR does not mean installed version updated.
6. P2: verify market price kind (sale/listing/reference), exact edition/printing, date, condition and provenance are visible; stale/unknown are not live-sale facts.
7. P2: test real-card render and slow networking/missing images/long Korean labels with local screenshots.

Official UX references: TCGplayer differentiates market/asking/recent sale and condition/printing/language. Collectr separates sealed/cards and portfolios. Android Accessibility guidance targets 48dp. Refer to official sources before further implementation.

Status: DRAFT/HOLD — PR and deterministic demo evidence only, not merged or verified on Lenovo.
