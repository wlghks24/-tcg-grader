---
name: tcg-card-variant-resolution
description: Resolve TCG card printing, parallel, artwork, language, edition, set, and card-number ambiguity without silently merging unlike cards or poisoning confirmed identity learning.
version: "1.0.0"
---

# TCG Card Variant Resolution

Use this skill whenever scanner results or market evidence may mix standard, holo, reverse holo, foil, parallel, promo, full-art, alternate-art, special-art, manga, language, edition, or set variants.

## Rules
1. Card number alone is not sufficient when multiple print variants share the same number.
2. Preserve game, card name, exact card number, set/edition/language, printing variant, condition, grader, and grade as separate identity dimensions.
3. When multiple variants remain plausible, hold aggregate pricing and ask for explicit user confirmation.
4. A user selection may re-query the market for that variant, but it does not become a verified learning label until the existing confirmation path accepts it.
5. Never choose the most expensive variant as the default.
6. Never broaden a selected edition or language merely to obtain more price rows.
7. Wrong-card, wrong-set, wrong-edition, and wrong-variant rows remain visible only as clearly marked reference data when appropriate; they cannot enter the headline recommendation.

## UX
Show the ambiguity before the recommendation. Use a short variant selector populated only from observed/allowlisted variant keys, then rerun the existing evidence pipeline.

## Verification
Test ambiguity, exact variant selection, unknown variant evidence, edition mismatch, card-number collision, and raw-versus-graded separation.
