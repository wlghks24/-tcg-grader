---
name: tcg-seller-provenance
description: Preserve marketplace, seller/store, listing URL, evidence class, and source lineage for TCG prices without inventing missing seller identities.
version: "1.0.0"
---

# TCG Seller Provenance

Use this skill for selling venues, seller/store labels, marketplace comparisons, and source-by-source price cards.

## Rules
1. Marketplace/source and seller/store are different fields.
2. Show seller/store only when the provider explicitly supplies it.
3. Never derive a seller name from a marketplace hostname, search query, title fragment, or user-selected country.
4. Preserve a public source URL when one is available.
5. A per-source median may summarize several sellers, but the UI must label it as a source aggregate and may show a bounded seller sample/count.
6. Seller identity never upgrades asking-price evidence into completed-sale evidence.
7. Missing seller metadata is valid; display the marketplace aggregate instead of fabricating a store.
8. Exported evidence must retain source, seller when known, evidence tier, date/freshness, price, and URL.

## Verification
Test structured seller extraction, missing seller safety, per-source seller counts, export fields, and HTML escaping of seller names.
