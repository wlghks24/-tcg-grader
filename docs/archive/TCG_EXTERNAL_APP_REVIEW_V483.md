# TCG external app review V483

Reviewed 2026-10-08 for the local-only tablet TCG Grader.

## Scope

This follow-up review focused on card measurement, card identity, price presentation, seller/source provenance, condition/language/printing comparability, local price history, and tablet UI.

Primary product/documentation pages and current GitHub projects were used for implementation decisions. Google/web, Instagram-indexed pages and YouTube search were used as discovery channels only. No social/search snippet is promoted into a card price, sale fact, grade, release fact, or market direction.

## Current external patterns

### TCGplayer
Official app/help pages emphasize:
- Market Price, Listed Median and most recent sale as different values.
- Condition, language and printing as separate scan/listing dimensions.
- Verify the set/printing after scanning because visually similar reprints can be confused.
- Exportable card-list workflows.

Useful pattern adopted:
- make condition, language/edition and printing visible before price interpretation;
- keep completed sales, API/market reference and asking prices separately viewable.

### Ludex
Official scan/price and Price Report pages emphasize:
- recent marketplace sales;
- raw/graded, condition and parallel filters;
- time-window price reports;
- explicit parallel selection/correction.

Useful pattern adopted:
- exact printing and condition controls;
- direct source/marketplace evidence links.

### Collectr
Official pages emphasize:
- raw and graded values;
- sold/listing comparisons;
- longer price-history views;
- collection/search history and export.

Useful pattern adopted:
- bounded recent measurement shortcuts;
- local recommendation snapshots with explicit “device observation” labeling.

### PriceCharting
Official app/collection pages emphasize:
- condition/grade-aware pricing;
- price history;
- scanner confidence/review;
- grading-opportunity/economics surfaces.

Useful pattern adopted:
- continue fail-closed identity review and exact grade separation.
Not adopted:
- no profitability guarantee or automatic grading recommendation from incomplete evidence.

## Open-source patterns reviewed

Projects discovered through current GitHub search included:
- the_tin: local/on-device workflows, exact variants/conditions, CSV import/export, staging/batch concepts and price history.
- pokecollect: exact printing resolution, uncertain-field review, price history and mobile-first PWA patterns.
- deckpal: variant-level catalog and dated price history.
- local-mtg-scanner: local-first scanning, exact printing/condition filters and price-history patterns.

These were used as architecture/UX references only; no third-party proprietary dataset or hidden credential path is copied into the repository.

## Gaps found after V482

1. The repository already had canonical NM/LP/MP/HP/DMG, language and printing identity rules in market_price_context_v433.py, but the multi-market UI did not expose the condition dimension.
2. The existing KR/JP/US selector actually represents card language/edition, but the UI label “시장” made that meaning unclear.
3. Source cards showed marketplace prices but did not clearly surface seller/store provenance when a provider supplied it.
4. Completed-sale/API-reference/asking evidence was internally separated, but users could not explicitly switch the displayed evidence tier.
5. There was no bounded device-only recent lookup/history surface for measured cards.

## Adopted in V483

### Exact price context
- Reuse canonical CONDITIONS from market_price_context_v433.py.
- Add visible condition and printing filters.
- Keep existing region selector as language/edition context and relabel it accordingly.
- Unknown or mismatched condition/printing remains reference-only and cannot enter the headline recommendation.
- Cache keys include condition and printing.

### Seller/source provenance
- Preserve structured seller/store names only when the provider supplies them.
- Keep marketplace/source separate from seller identity.
- Add source-by-evidence-tier medians and direct public source links.
- Never infer seller identity from a hostname, query or title.

### Evidence-tier UI
- Let users view completed transactions, API reference prices or asking/listing prices independently.
- Recommendation calculation remains on the strongest evidence tier and is not rewritten by the display filter.

### Local lookup history
- Store only compact, bounded exact-card lookup snapshots in browser localStorage.
- Replace same-card/same-day snapshots and cap total history.
- Show 7D/30D change only when an older local snapshot exists.
- Clearly label the history as values observed on this device, not official transaction history.
- Keep a bounded recent measurement shortcut list that reruns the normal verified evidence pipeline.

## Deliberately not adopted

- No cloud collection sync or telemetry.
- No social feed or community marketplace.
- No automatic seller account integration or listing creation.
- No invented market price when exact condition/printing evidence is absent.
- No automatic substitution to the most expensive or nearest variant.
- No non-core TCG grading activation.
- No claim that local lookup history is market transaction history.

## Repository skills added

- tcg-condition-language-pricing
- tcg-seller-provenance
- tcg-local-price-history

## Completion criteria

- condition/printing filter tests pass;
- seller provenance and evidence-tier breakdown tests pass;
- local-history UI stays bounded and local-only;
- market auto-repair keeps the updated API contract;
- skills are mirrored and routed;
- repository integrity, tablet runtime, sync, SELFREFINE, CodeQL and collection verification all pass before merge;
- physical tablet application remains separately verified after update-now.
