---
name: tcg-purchase-evidence
description: Build and validate TCG purchase-source UI and data across official pages, marketplaces, map discovery, nearby shops, retailer categories, and inventory verification boundaries.
version: "1.0.0"
---

# TCG Purchase Evidence

Use this skill for online purchase links, nearby stores, retailer directories, store maps, stock reports, purchase probability, and card-to-shop handoff.

## Source classes
- official: product/store information from the game or retailer owner;
- marketplace: public product/search catalog;
- map: nearby-store discovery only;
- tracker/search/social: reference signals only unless an explicit inventory contract verifies stock.

## Rules
1. Registry core/promoted games with purchase capability may receive official, market, and map routes.
2. WATCH games remain excluded from real-time purchase search until promoted by the existing registry policy.
3. A map result proves a location candidate, not TCG stock.
4. An official chain directory proves the branch exists, not that a card is in stock.
5. Never convert reviews, Instagram posts, YouTube videos, blog posts, or search snippets into verified inventory.
6. Keep online/offline filters and retailer categories separate.
7. Preserve exact game/card query when handing a measured card to the purchase finder.
8. Nearby sorting uses device/browser coordinates locally; do not persist precise location in repository data.
9. Show inventory status and verification age when available; otherwise label it unverified.
10. Never fabricate price, stock, opening hours, or distance.

## Verification
Test promoted-game coverage, WATCH exclusion, URL safety, map template safety, inventory_verified=false for generated routes, card-to-purchase query handoff, and offline/online filtering.
