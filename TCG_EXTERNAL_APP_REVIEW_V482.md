# TCG external app review V482

Reviewed 2026-10-08 for the local-only tablet TCG Grader.

## Research method

Primary product claims were taken from current official product/help pages where available. Google/web search, Instagram-indexed pages, YouTube search, and community discussions were used as discovery/supporting signals only. Social/search snippets are not treated as authoritative price or grading evidence.

## Products and patterns reviewed

### Ludex
Official pages:
- https://www.ludex.com/scan-and-price/
- https://www.ludex.com/features/
- https://collections.ludex.com/

Useful patterns:
- scanner detail flow asks the user to verify card details and estimated price;
- explicit Parallel drop-down instead of silently choosing a variant;
- recent sale/price report;
- collection management and CSV export.

### Collectr
Official page:
- https://www.getcollectr.com/pro

Useful patterns:
- long price-history visibility;
- saved search/history and advanced filters;
- collection export.

### CollX
Official pages:
- https://www.collx.app/
- https://www.collx.app/collx-pro

Useful patterns:
- scan -> value -> collection workflow;
- CSV export and set/checklist ownership;
- marketplace/social features exist, but those are out of scope for TCG Grader.

### PriceCharting
Official pages:
- https://www.pricecharting.com/page/app
- https://www.pricecharting.com/page/collection-tracker

Useful patterns:
- low-confidence scan results explicitly tell the user to verify;
- historical collection values;
- sale/profit tracking and grading-opportunity surfaces.

## Community failure patterns reviewed

Recent collector discussions repeatedly mention:
- stale sales being shown as if current;
- asking prices being mistaken for actual market value;
- wrong parallel/variation identification;
- incomplete databases;
- desire for local CSV ownership/backup.

Community reports are treated as problem-discovery signals only, not as factual evidence for a specific card value.

## Adopted in V482

1. Market freshness
   - Normalize provider observation dates.
   - Reuse the existing repository FRESH/AGING/STALE/EXPIRED/UNKNOWN contract.
   - Show freshness beside source prices.
   - Downgrade recommendation confidence when supporting dates are old or unknown.

2. Variant resolution
   - If one card number yields multiple observed print variants, do not silently aggregate them.
   - Show a variant selector and rerun the same bounded market evidence pipeline for the selected printing.
   - Existing user confirmation remains the learning boundary.

3. Local evidence export
   - Add local CSV/JSON download for the measured card and multi-market evidence.
   - Include source, evidence class, source price, freshness, recommendation contribution and public source URL.
   - No cloud upload or background sync.

4. Repository skills
   - tcg-market-freshness
   - tcg-card-variant-resolution
   - tcg-local-evidence-export

## Deliberately not adopted

- Direct eBay/marketplace selling: changes the product into a transaction system and requires credentials/payment/seller-state review.
- Social/community feed: unrelated to the core grading/evidence workflow.
- Blind "AI value" override: conflicts with evidence/provenance rules.
- Automatically picking the most expensive parallel: explicitly forbidden.
- Cloud collection sync: current tablet runtime remains local-only.

## Completion criteria

- targeted collector and UI tests pass;
- agent skill mirror/router guard passes;
- repository integrity and runtime delivery pass;
- Tablet GPT/TCG Grader sync generation covers the changed runtime paths;
- full required PR checks pass before merge;
- physical tablet remains separately verified by the user after update-now.
