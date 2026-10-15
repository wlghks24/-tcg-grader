# V637 — 2026-10-15 dual-video TCG mobile-market review

## Evidence and scope
- Recording A: 96.1 seconds, 512×1108 / 30fps. Pokémon-oriented "스니덩크 전체 시세" list. Indices shown through 415.
- Recording B: 40.93 seconds, 512×1108 / 30fps. ONE PIECE-oriented list. Indices shown through 141.
- The recordings show another app's market-list UI; this does **not** prove that TCG Grader's own UI has the same defects.
- A displayed index is **not** a verified unique-product count; video alone cannot prove image accuracy, transaction accuracy, provenance or a server-side crash.

## Observed presentation risks
1. Product titles truncated to ~2 lines and currencies/edition prices squeezed together.
2. Single/box/pack/promo/sets appear in a homogeneous list, weakening disambiguation.
3. Fixed bottom navigation visually overlaps some visible list rows.
4. Repeated "불러오는 중" states; user scrolling or network delays may explain these. No freeze/crash is proven.
5. At a glance the source dates, sale-versus-ask tier and item condition are not distinguishable.

## Current TCG Grader code audit
- `multi_market_prices.js` already separates completed/API/asking evidence and condition/printing, and contains exact-card recommendations and local history.
- Previous `load` had no response-order guard; a previous search could overwrite a more recent one.
- Old recommendation/grade panels could remain visible while a new query failed, despite the summary switching to failure. This is risky for price decisions.
- `multi_market_prices.css` used 8.5–10px metadata and clamped product titles.

## V637 changes
- Abort older requests where supported and additionally enforce monotonically increasing request IDs. Reject late responses even if a fetch mock/provider ignores abort.
- Clear results and dependent price/grade panels whenever new query begins, query empties, or the active request fails.
- Expand mobile titles, wrap prices, increase source metadata font size and improve tap areas without changing raw evidence, recommendation math or source allowlist.
- No new API services, credentials, trackers, uploads or paid infrastructure.

## External patterns checked
- TCGplayer: completed-sale market price differs from live listing/lowest listing; product condition, language and printing must match. https://help.tcgplayer.com/hc/en-us/articles/213588017-TCGplayer-Market-Price
- PriceCharting: recent completed sales, age weighting and anomalous-sale filtering. https://www.pricecharting.com/page/methodology
- Collectr: sealed/single separation, language/price/grade filters and portfolio organization. https://getcollectr.com/track.html
- SNKRDUNK TCG category: sealed box, pack and single filters. https://snkrdunk.com/en/magazine/2023/06/22/trading-cards-tab-is-now-live-on-the-snkrdunk-app/
- TCG Hub on Play Store: card/box market charts, grading, collection and alerts as comparison, without assuming its advertised pricing reliability. https://play.google.com/store/apps/details?id=kr.tcghub.app

## Next priorities (not claimed complete)
P0: Validate `node test_multi_market_video_ui_v637.js`, existing runtime/integrity/CodeQL checks and tablet actual render before merging.
P1: On BOX catalog, separate BOX/pack/single/promo/collection, KR/JP/US/CN edition, exact set code, sealed status, bundle count, source date, original currency and FX timestamp. Display observed low/high only from **matching verified evidence**; hold sale recommendation when there are not sufficient comparable recent prices.
P1: Mobile row visibility, bottom safe-area padding and actual PWA scrolling/performance on Lenovo tablet (videos are iOS and not execution evidence for Lenovo).
P2: Paginate/virtualize long source lists, preserve sort/filter/scroll position, and add measured loading/error retry controls.
No price or availability is fabricated and no copyrighted images are copied from the recording.
