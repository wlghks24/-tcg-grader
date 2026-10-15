# TCG BOX pricing V572 — verified scope and release HOLD (2026-10-15)

## Findings from actual protected-main inspection (SHA a7f9c6e2e14770c10a8a676ee3d860e7c8aa5d13)
- Card price already uses \`multi_market_price_collector.py\`, \`multi_market_prices.js\` to expose comparable-tier low/high and a source-median **trade reference**; this is not independently verified seller net proceeds.
- BOX catalog \`renderBoxKnowledge()\` in \`index.html\` showed primarily \`LEARNING_PRICE_DATA[x.name]?.retail\` (official release price), not the exact BOX's separate observed lowest/highest listing and recommendation.
- \`market_prices.json\` contains \`REGION|name|BOX\` entries with \`display\` price strings; some are single source quotations and some are published ranges. These must never be promoted to independent verified trades or universal marketplace extrema.
- \`market_watch.json\` provides product leads and official/MSRP context, not confirmed sales.
- Search-result \`sold/completed/판매완료\` terms in \`multi_market_price_collector._price_evidence_class()\` currently classify snippets as completed **signals**. This is not independent receipt/transaction verification; do not treat as verified completed transaction when building BOX seller recommendations.
- Existing generic card name-only collector refuses market aggregation without a card number, so it cannot be repurposed for BOX automatic price discovery without a dedicated product identity+sealed/unit gate.

## Change in this PR
- Show three separate BOX prices **inside existing BOX cards** (low, high, suggested selling price) using existing background-loaded canonical \`market_prices.json\`. No manual product-by-product entry required for visibility.
- When a product has a single dated, trusted-source snapshot, label it \`관측가\`; minimum and maximum remain blank. When a trusted snapshot contains an explicit range, show endpoints **with an explicit disclaimer** that these are published source range, not full-market extrema.
- A selling reference may only be derived from a future **upstream-reviewed** \`price_observations\` contract: exact \`region|name|BOX\`, one sealed BOX per unit, KRW, date within 30 days, source URL, 2 independently verified completed sales from at least 2 market hosts, deduplicated sale IDs, one observation within 7 days. Use median of independent source medians. Missing or stale evidence = recommendation HOLD.
- Responsive 3-column micro-price panel; formatting remains local and no original card image/private data is introduced.
- New deterministic Node regression under \`execution/\`; static runtime code digest pinned in \`integrity_manifest.json\`. Exact source JavaScript executed with isolated mock document and 12 direct input tests on 2026-10-15 (not equal to integrated tablet/browser test).

## Proof vs NOT PROVEN
- PROVEN (static/isolated): JavaScript parses/executes in a fake DOM; basic cases including old/future quotes, mismatched game, mixed 8BOX, non-sealed, fake completed proof, mirror duplicate, independently completed evidence verified in a deterministic mocked fixture.
- NOT PROVEN: any real new BOX sale-price collection; existence of live \`price_observations\` in current catalog (none established); actual Lenovo screenshot/touch/UI; all repository tests/CI until fresh exact-head workflows run; before/after performance; one-click upload/update via tablet.
- Do NOT describe a sample two-source calculation as a real current market recommendation.
- This change does **not** solve prohibited/blocked API sources, platform transaction verification, fully automated price observations, China edition parity, price including shipping/platform commissions, or PDF/CSV exports for BOX.

## Priority defects / next gates (no assertion weakening)
- P0: independent official or trusted marketplace evidence adapter, permission-aware and bounded; distinguish ASKING, API MARKET REFERENCE and VERIFIED COMPLETED sale; authenticated endpoints only with user-controlled free credentials; 403/429 -> cooldown. Never scrape protected pages or infer completion from snippets. Respect privacy and ToS.
- P0: canonical match sealed BOX vs 8BOX/case/display/promotional bundle and distinguish KR/JP/US/CN-S/CN-T; exact set codes and language when supported. Current UI has KR/JP/US; China separate draft.
- P0: full current-head CI including integrity, SELFREFINE, tablet alignment/immutable successor contract, security. No merge without verified checks.
- P1: local browser smoke on widths 430, 800, 1280; source/date badges, focus/keyboard, overflow, refresh/out-of-date PWA service worker, mixed-card UI, navigation.
- P1: Lenovo physical device online/offline proof, auto-refresh and recovery; report separately.
- P2: seller-specific estimated *net* amount after item price, shipping, commission, fees and currency; conditional recommendation if verified user costs available.

## Competitive comparison references (architecture guidance, not copied datasets)
- TCGplayer distinguishes TCG Market Price (recent completed sales), Lowest Listing (price + shipping), Last Sold and sealed-product listings: https://help.tcgplayer.com/hc/en-us/articles/201914668-Best-Practices-for-Pricing-Your-Items
- TCGplayer's dynamic Low/High/Market strategy and fallback: https://help.tcgplayer.com/hc/en-us/articles/16007140992791-Price-Settings-and-Updates
- PriceCharting sealed Booster Box pages separate historic completed sales and current market price: https://www.pricecharting.com/game/pokemon-crimson-invasion/booster-box
- Prior repository audit: \`TCG_EXTERNAL_APP_REVIEW_V483.md\` covers TCGplayer, Ludex, Collectr, PriceCharting and local open-source patterns.

## Final gate
DRAFT ONLY / DO NOT MERGE / NO TABLET DEPLOYMENT unless fresh exact-head CI and real device evidence warrant release.
