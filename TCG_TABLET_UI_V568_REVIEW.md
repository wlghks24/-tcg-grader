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
- Checked extension is CSS-only, balanced braces, no script/url/import, 2-column fallback and >=44px market-card action targets.
- Tested a separate, **non-production** interactive HTML UI prototype with Playwright at 430px/800px: no horizontal document overflow; category and 5-tab routing, card/BOX filter, favorite save, local image preview, and store-list interactions exercised without JavaScript errors.
- The standalone prototype and these tests do **not** constitute a true integrated app test.

### Merge / deployment HOLD checklist
- [ ] Existing tablet navigation / market / grading regression suite passes against **exact PR head**, not an older SHA.
- [ ] Inspect actual app (not standalone prototype) at 360/430/800/1280 CSS px for overlap, long Korean labels, grid overflow, hidden panels, bottom dock, focus and reduced motion.
- [ ] Verify service worker cache/update behavior after changed CSS; stale cached UI must not be called an update success.
- [ ] Validate category -> feature -> back and home-reset, and all existing legacy tools remain reachable.
- [ ] Preserve WATCH/promoted/grade gates, completed-sale vs listing tiers, variant-specific pricing, and image provenance.
- [ ] On Lenovo real device confirm touchscreen, portrait/landscape and scroll behavior and capture before/after evidence privately.
- [ ] Resolve prior v470/v471 navigation orphan-panel issue in a separate, reviewed runtime JS + successor-sync change; not silently in this CSS-only PR.

**Status:** DRAFT/HOLD. No claim of device installation, completed integration test, live market result, or production approval.
