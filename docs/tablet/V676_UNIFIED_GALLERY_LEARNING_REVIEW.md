# V676 — Unified Tablet Evidence Gallery / Local Learning Gap (audit-only)

Date: 2026-10-26 KST. Source ancestry: V673 #840 → V674 #845 → V675 #848 → V676. Protected main c5bf5608 unchanged.

## Existing capabilities inspected
- `social_event_discovery.py`, `event_quick_watch.py`, `execution/official_social_discovery.py`: already collect official/social leads, with evidence gates; social hints remain candidates, not official confirmed events.
- `promo_events.json`, `releases.json`, `market_watch.json`: canonical or listing-like sources exist but are not evidence of actual completed sale, card value, print run or verified event schedule unless explicit verification is present. Publication date != event date.
- `tablet_image_auto_v2.py`, `tablet_image_library_v1.py`, `execution/tablet_catalog_bridge.py`: existing local image collection and exact source ↔ image matching. Do not import image from wrong regional printing.
- `execution/tablet_local_automation.py` + `execution/tablet_local_learning.py` + image autonomy: single Termux six-hour scheduler, guarded model training only when independently verified eligible samples and resources are sufficient. Do not duplicate scheduler or override readiness.
- `tcg_card_detail_v566.js` already contains evidence-gated card pricing and grade UI. This opt-in gallery does not remove or overwrite that implementation.

## V676 implementation (non-production)
A standalone new responsive gallery (`tablet_unified_gallery_v676.html`, `.css`, `.js`) presents card, promo, BOX, products and verified-source event entries in one glance. Filters are game (Pokémon/One Piece/Naruto), edition (ALL/KR/JP/US/CN), kind and searchable code/name/series. **CN is one tab**; CN-S and CN-T + HK/TW edition identity survives in records.

The page uses existing same-origin, read-only `/api/local-card-images/catalog-links`, `/promo_events.json`, `/market_watch.json`. No new browser API, paid provider or external image request. Image tiles are served by the existing integrity-checked `/api/local-card-images/file/<32 hex>` endpoint **only when exact unique source_record_id + photo ID, game ID, edition and kind agree and the bridge marks the photo CODE_MATCH**. Wrong, missing and ambiguous matches render a placeholder; orphan local images remain separate.

No sales, estimated grades, ROI or future prices are invented: listing price is explicitly labeled as unverified; source and verified sale are separated; card generation metadata appears only if stored by the image provider. Recorded event date is hidden for tracker-only/unannounced and invalid calendar values. Navigation does not mutate installed index/layout/DOM; JS uses textContent/DOM nodes, not innerHTML. CSP confines requests/images/scripts/styles to same-origin and blocks forms.

`execution/tablet_learning_gap_v676.py` analyzes existing Query/Job labels as pure function, never changes training status or labels. 1,000 independent samples plus existing positive/negative readiness are required; 309 legacy/unverified labels do not qualify. Missing input is HOLD. Even when observed eligible, **training_permitted and model_promotion_permitted are always false** in this observer: only existing Termux safety gates may decide. This module does not create another daemon, cron, cloud workflow or Android process.

## Source expansion decisions (review-only)
- Official Pokémon product/events: pokemon-card.com / pokemon.cn / asia.pokemon-card.com and locale-specific publishers; One Piece Korean cardlist/products/topics/events; Naruto via verified official publisher only. Add image rights/license review before downloading official artwork. Respect robots/Terms/rate limits, 403/429/Retry-After and existing storage budgets. No account scraping, logins or anti-bot bypass.
- Event/collaboration source: separate date of announcement, event start/end, promo entitlement, image attribution, country and verified publication. A social post alone does not establish a confirmed date.
- Card/BOX: join on game + edition + kind + exact product/card code; require separate image front/back and certified grade records. Generation is series metadata, not deduced from photo color.
- Market: asking price vs sold price vs graded-card actual sale vs forecast must be separate. Avoid displayed forecast without time window, sample size, freshness and holdout evidence.
- Learning: existing supervisor continues bounded outcome collection; use gap report to prioritize **genuine** independent reviewed observations. Never duplicate samples, fabricate outcomes or lower thresholds.

## Multi-perspective review / acceptance
1. UI accessibility: 360px, 620px, 1024px review, 44px controls, keyboard focus and no horizontal overflow/device jank.
2. Evidence: no cross-game/edition product photo; ambiguous duplicates HOLD; source-linked image is still not verified physical printing.
3. Security/privacy: reject hostile links, no reflected HTML, local-only API, no external images or credentials.
4. Collection: event/collab/official/social publisher provenance, timeouts and licensing tested separately; no production scraping activation.
5. Learning: small/legacy/malformed label populations remain HOLD and last-good untouched; no hidden synthetic grades or manual override.
6. Operations: verify GitHub exact HEAD full CI, previous immutable proofs, then real Lenovo Termux 6h supervision, cold start, actual collection and image hash readback, backup/restore before enabling or merging.

**Remaining blockers:** New gallery is opt-in and not linked from the immutable original index; source-level V675 parser is still shadow-only; current event image data do not provide an independently certified exact event-photo binding; live sold-price/grade accuracy, latency, memory, offline UX and model learning evaluation are unverified. No production merge, auto-install or last-good model promotion approved.
