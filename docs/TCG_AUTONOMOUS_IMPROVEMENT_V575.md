# TCG Grader — Proactive development & QA V575
Updated: 2026-10-15 KST. Source contract: AGENTS.md and directives/TCG_RELIABILITY_SOP.md.

## Required loop on each change
1. Recover last-good, exact SHA, P0/HOLD/DEFERRED and all previous error logs before doing anything.
2. Inspect code, official documentation and maintained license-compatible free open-source examples, not just user's named functions.
3. Discover missing features independently by checking full paths: cards, BOX, local collection, price source, sale evidence, variants, scanning, UI, tablet and offline update.
4. Rank hypotheses by evidence and user impact. Define minimum patch, verification test, rejection criteria and rollback before coding.
5. Patch only the smallest approved area; never autonomously change grading calibration, upload personal data or weaken price/source/security gates.
6. Execute targeted checks then all current-head CI; test malformed, stale, wrong product, network failure, duplicates, safe rollback and local browser/device when available.
7. Record evidence, independent re-review and real measurements. An internal score is not a market value or a real-device proof.
8. Publish a clear P0/P1/P2 result using V573 machine audit and V575 responsive self-contained HTML, with before/after comparison only if earlier evidence exists.
9. Do not merge to protected main, claim installation or promise continuous background improvements without actually scheduled/running authorized tools.

## Automatic, bounded, free-first reporting
- The source and tests are in execution/tcg_system_audit_v573.py and execution/tcg_quality_report_v575.py.
- Run python execution/tcg_quality_report_v575.py --html-out .tmp/tcg-quality.html --json-out .tmp/tcg-quality.json locally.
- Add --baseline-json /path/to/previous-result.json for actual numeric differences; never infer earlier results.
- Relevant PR edits and explicit workflow dispatch run TCG System Evidence Audit V573 in existing source CI.
- Outputs are retained for 7 days as build artifacts, not published as verified tablet state.
- No cloud AI inference, paid provider, new installed background service, social scraping or source rewrite is initiated.

## Competitor patterns, adoption boundaries
- TCGplayer differentiates sale-based Market Price, most recent sale, and listed median; fee/shipping also matters.
- Collectr shows card/sealed portfolio views, language/printing filters and multi-game search.
- Open-source pokecollect shows locally mirrored catalog, scanning review, source-specific prices and price history; do not enable its optional paid/cloud Gemini path.
- Open-source local-mtg-scanner prioritizes local/offline collection, printed-card identification and history. Review license and project maintenance before copying anything.
- Never present vendor listings as completed sales, merge JP and CN variants, assume live stock or fabricate a sales recommendation.

References:
https://help.tcgplayer.com/hc/en-us/articles/222376867-What-do-the-different-price-points-on-TCGplayer-com-mean
https://help.tcgplayer.com/hc/en-us/articles/201914668-Best-Practices-for-Pricing-Your-Items
https://www.getcollectr.com/track.html
https://github.com/Trust1509/pokecollect
https://github.com/McDandle/local-mtg-scanner

## V575 confirmed baseline / HOLD
- 30 registered TCG games. 32 static BOX showcase items. 25 stored BOX price entries.
- 12/32 static BOX items match a stored price by exact game, edition, country and name: 37.5% linkage, not price correctness.
- 0 stored BOX entries currently have reviewed structured completed-sale evidence. No live seller-recommended price is established.
- CN-S/CN-T fixed showcase, true tablet offline/touch/layout proof and sale provider integrations are incomplete.
- Static regression PASS never substitutes for real Lenovo or source-confirmed sale proof, and cannot justify 95/100 product-completion grade.

## Scope / honesty
- V575 audit reads local code/evidence and emits HTML/JSON; it does not overwrite cards, code, device media, git main or market prices.
- The report escapes any source text and embeds no JavaScript, fonts, third-party requests or trackers.
- Improvement suggestions are deterministic proposals, not autonomously applied code or adaptive AI model learning.
