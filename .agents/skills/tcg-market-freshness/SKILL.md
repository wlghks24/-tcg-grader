---
name: tcg-market-freshness
description: Validate TCG price freshness, observation dates, stale evidence, source-date provenance, and confidence downgrades before any market value or trade-reference UI is changed.
version: "1.0.0"
---

# TCG Market Freshness

Use this skill for card/BOX prices, completed sales, API reference prices, asking prices, price history, and trade-reference recommendations.

## Required checks
1. Preserve the provider's observation or transaction date when available.
2. Normalize ISO, RFC-style, and bounded provider timestamps before computing age.
3. Never label the time a search ran as the time a completed sale occurred.
4. A live structured API may use the current observation date only for the API reference itself; keep its evidence class separate from a completed sale.
5. Reuse the repository freshness contract instead of inventing a second threshold system.
6. Show FRESH/AGING/STALE/EXPIRED/UNKNOWN to the user in understandable language.
7. Missing or old dates lower confidence; they never create a newer price.
8. Keep completed-sale, API-reference, and asking-price tiers separate.

## Recommendation rule
A headline trade reference must retain exact card identity and variant gates. Source freshness is part of confidence and provenance. Old or date-unknown evidence may remain visible as reference material, but the UI must make the limitation explicit.

## Verification
Add targeted tests for date normalization, unknown dates, live API observation freshness, stale confidence behavior, source breakdown output, and UI badges. Then run the normal market, runtime, integrity, and full regression gates.
