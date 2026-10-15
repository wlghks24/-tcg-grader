# V573 TCG app comparison and risk-led implementation guide
Reviewed: 2026-10-15 (KST)
Status: evidence-based research; NOT live price verification, emulator QA, or physical Lenovo proof.

## Official vendor patterns (product documentation, not copied code)
| Reference | Confirmed documented behaviour | Safe integration pattern |
|---|---|---|
| TCGplayer (pricing) | Market is recent completed sales; Most Recent Sale is separate; Listed Median reflects current asks; condition/printing filters matter. | Show listing minimum/maximum apart from sold median, link original source and explicitly HOLD where sale evidence is absent. |
| TCGplayer App | Scan -> verify version, language, condition, printing -> market price. Card scan may select an incorrect reprint. | Require explicit SKU/set/edition confirmation before price promotion; unverified scan is advisory only. |
| Collectr | Single-card/graded/sealed portfolio, scanning, item variants, daily-value history and charts. | Treat portfolio, verified sale evidence, historical price data and sealed boxes as independent surfaces. Never invent returns from listing prices. |
| PriceCharting | Sale history and volume, collection cost/sales/history; sold-listing pages may mix similarly named variants in raw listings. | Filter sealed single BOX identities and exclude loose packs, cases, foreign prints and accessories from comparisons. |
| eBay Product research | Up to 3 years of sold-data research, separate actual accepted-offer price, shipping and sell-through (requires product-appropriate account access). | Prefer independently verifiable sold events and shipping-inclusive price, without promising free unauthenticated API access. |
| Cardmarket official files | Free daily Price Guide and product-catalog download; deprecated API endpoints should not be depended on. | License/terms review before optional read-only official download adapter. Do not scrape blocked or paid datasets. |
| W3C WCAG 2.2 | Pointer target generally >=24x24 CSS px (or qualifying spacing), enhanced 44x44. | Aim for >=44px on tablet navigation; check DOM labels, focus order and narrow viewport overflow with a browser test. |

Sources:
- https://help.tcgplayer.com/hc/en-us/articles/222376867-What-do-the-different-price-points-on-TCGplayer-com-mean
- https://help.tcgplayer.com/hc/en-us/articles/115009506407-TCGplayer-App-FAQ
- https://help.tcgplayer.com/hc/en-us/articles/115009674788-Tips-for-Accurate-Scanning
- https://getcollectr.com/index.html
- https://www.pricecharting.com/page/collection-tracker
- https://www.ebay.com/help/selling/selling-tools/terapeak?id=4853
- https://news.cardmarket.com/en/Magic/were-making-the-price-guide-and-product-catalogue-available-for-download
- https://www.w3.org/WAI/WCAG22/Understanding/target-size-minimum

## Independent code/data inspection, current PR #691
- Exactly 30 registered TCG games in `tcg_game_registry.json`.
- 32 fixed `COUNTRY_BOX_DATA` items (KR 11, JP 11, US 10).
- 25 BOX price records in `market_prices.json`, of which only 12 exactly link to static catalog by game/region/name.
- Zero BOX records in the current dataset contain reviewed `box_price_evidence` rows, so a production selling recommendation is not evidenced.
- CN-S/CN-T catalog and country chooser are incomplete in the legacy UI; do not combine simplified/traditional markets.
- Existing V572 core change does not verify tablet frame timings, touch execution or offline service-worker runtime.

## Risk remediation queue (HOLD means not implemented)
P0: Distinguish completed sales, current asks, official MSRP and indicative prices; block false sale-price inference. V572 comparator gate and V573 read-only audit cover only the data-format aspect.
P0: Preserve historical signed sync contracts, manifest SHA, pinned runtime and protected main. CI required.
P1: Automatic collector should populate verified BOX observations per source under rules and rate limits, with deduplication, SKU/edition/printing/region and sale ID checks. Never relabel RSS/search snippets as completed sales.
P1: CN-S/CN-T catalog visibility, source-specific official language and region, release dates and sealed product photos. Existing core data coverage is currently insufficient.
P1: UI browser screenshot checks at 360/430/800/1280 CSS px, menu separation, enlarged touch controls, no horizontal clipping, contrast/focus, and offline retries. CI static scan is not a substitute.
P2: User-owned photo cache on tablet only; portable CSV evidence history, fee/shipping-aware optional net reference and multi-source price history, all free-first.
P2: Measure request timeouts, retries, data volume and cold-start rendering on Lenovo; keep prior safe version until proof.

## Automatic read-only audit
`execution/tcg_system_audit_v573.py` compares static catalog identities with registry and locally stored prices, flags stale evidence, country gaps and unverifiable recommendations. Workflow `TCG System Evidence Audit V573` runs in PR and is scheduled daily if merged to default branch; emits a 7-day retention report. It never creates or edits prices, pushes repository content, or confirms real-world sales.

## Evaluation principle
Functional review scores are permitted only for verified test dimensions: parsing, identity, source date, UI DOM, runtime, security, distribution. The composite completion score is HOLD if device tests or reliable transaction data are missing, regardless of the number of passing static tests. No 95/100 award without measured evidence.
