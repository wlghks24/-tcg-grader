# TCG external app and discovery review V483

Reviewed 2026-10-08 for the local-only tablet TCG Grader.

## Sources and confidence

Primary product behavior is taken from current official product/help pages. Google search, Instagram-indexed pages, YouTube search, blogs, and community posts are discovery signals only. They never become card identity, price, grading, stock, or purchase facts without a stronger source.

Official references reviewed:
- Ludex Scan and Price: https://www.ludex.com/scan-and-price/
- Ludex Collection Value: https://help.ludex.com/en_us/understanding-your-ludex-collection-value-Bkt7fzTec
- TCGplayer scanning tips: https://help.tcgplayer.com/hc/en-us/articles/115009674788-Tips-for-Accurate-Scanning
- TCGplayer Scan & Identify: https://help.tcgplayer.com/hc/en-us/articles/27303403772823-How-To-Use-Scan-Identify
- TCGplayer App FAQ: https://help.tcgplayer.com/hc/en-us/articles/115009506407-TCGplayer-App-FAQ
- Dex scanner: https://dextcg.com/help/collection/scanning-your-cards
- CollX FAQ: https://collx.app/faq

## Cross-app patterns worth adopting

### Exact card context before price
TCGplayer explicitly asks users to verify set, printing, language and condition because repeated artwork can be misidentified across sets. Dex exposes expansion, rarity and price then lets the user narrow by expansion/rarity/variant. CollX exposes multiple reprint/parallel choices instead of silently deciding.

V483 response:
- keep game, card name/number, edition, generation/set, grade and price as separate fields;
- Pokémon generation keeps the existing evidence-backed runtime;
- ONE PIECE uses exact card-number prefixes only for set-family context;
- NARUTO/other games do not receive an invented generation.

### Card detail to shopping
Ludex places recent sales, price report, card info and Shop on the card detail flow. TCGplayer exposes market/current-sale context after identification.

V483 response:
- add online purchase and nearby-store actions directly from the measurement result;
- copy the confirmed card name/number into the existing purchase finder;
- preserve online/offline and official/market/map source classes;
- never claim map/store discovery proves inventory.

### Purchase coverage beyond the original three games
The repository registry already allows purchase capability for promoted games, but the committed purchase_sources.json still contained only Pokémon, ONE PIECE and NARUTO rows.

V483 response:
- materialize official, public-market and map-discovery routes for every core/promoted purchase-enabled registry game;
- WATCH games remain blocked from real-time purchase search;
- generated map rows always remain inventory_verified=false.

### Price provenance in the grading cockpit
V482 already added freshness and variant correction to the detailed market panel. V483 mirrors freshness/age and public source links into the compact grading cockpit so the user does not need to jump between panels to understand where the number came from.

## Instagram and YouTube boundary

Instagram and YouTube searches are useful for discovering workflows, demonstrations, shop reports and user pain points. They are not authoritative evidence for card identity, exact set, market value, store inventory, or official release facts. V483 therefore does not promote social/video snippets into verified data.

## Repository skills added

- tcg-card-context
- tcg-purchase-evidence

These complement:
- tcg-market-freshness
- tcg-card-variant-resolution
- tcg-local-evidence-export

## Deliberately not adopted

- automatic highest-value variant selection;
- social-video popularity as a price multiplier;
- map/business presence as verified stock;
- cloud purchase-history sync;
- direct marketplace selling/payment handling;
- generation labels for games without a repository-backed generation model.

## Completion gates

- purchase source materialization covers all core/promoted purchase-enabled registry games;
- WATCH remains excluded;
- card cockpit has game + evidence-safe generation/set context;
- card-to-purchase handoff preserves card name/number;
- compact source cards show freshness and public source link when available;
- new skills pass mirror/router quality checks;
- integrity, runtime, Tablet GPT sync, full regression and required PR checks pass before merge.
