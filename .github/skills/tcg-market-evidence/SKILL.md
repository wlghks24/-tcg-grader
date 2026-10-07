---
name: tcg-market-evidence
description: 'Handle TCG market discovery, new-game WATCH/promoted decisions, prices, releases, promos, events, collaborations, retailer coverage, source freshness, and multi-source crosschecks for KR/JP/US.'
---

# Market Evidence and New TCG Discovery

## Evidence hierarchy
Prefer:
1. Official game/publisher pages.
2. Official news and organized-play pages.
3. Official social channels.
4. Major marketplaces/price guides.
5. Established retailers/distributors.
6. Community/social sources as supporting evidence only.

## Required rules
- Record source URL, verification timestamp, region, and lineage.
- Freshness is mandatory for market activation signals.
- Fallback/mirror sources sharing one lineage count once.
- Missing coverage is a `coverage_gap`, never silently "collected".
- WATCH candidates require a real official source plus independent market/organized-play/catalog evidence.
- Promotion requires current evidence and registry review.
- Never auto-enable grading for a newly promoted game.

## Price rules
- Separate language, condition, printing, raw/graded state.
- Use verified history only for trend windows.
- Treat surge/drop as a recheck trigger, not a trading recommendation.
- Never guarantee profit or infer market direction from one source.

## Coverage
For promoted games, track official home, official news, official social, publisher, tournament/event, collaboration, promo distribution, limited product, and retailer coverage across applicable KR/JP/US regions.
