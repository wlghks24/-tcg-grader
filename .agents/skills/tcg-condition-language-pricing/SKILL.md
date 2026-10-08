---
name: tcg-condition-language-pricing
description: Keep TCG raw-card market values separated by condition, language/edition, and printing so unlike copies never share a headline recommendation.
version: "1.0.0"
---

# TCG Condition / Language / Printing Pricing

Use this skill when changing card-market searches, scanner corrections, price summaries, or trade-reference UI.

## Exact-comparability rules
1. Treat condition, language/edition, and printing as independent identity dimensions.
2. Raw conditions use the repository allowlist: NM, LP, MP, HP, DMG.
3. A user-selected condition may enter the recommendation only when the source explicitly carries or clearly states that condition. Unknown condition remains reference-only.
4. A user-selected printing/variant may enter the recommendation only when structured metadata or bounded title evidence matches it. Unknown or mismatched printing stays reference-only.
5. Region selectors represent card edition/language, not seller geography. Never infer seller country from the requested edition.
6. Do not reuse search terms as evidence that a listing actually matches the requested language, condition, or printing.
7. Graded-card prices stay separate from raw-condition prices.
8. Never substitute the most expensive, nearest, or most common variant just to avoid an empty result.

## UX
Make condition and printing visible before the recommendation. Explain how many observations were excluded by exact filters. Keep language/edition context visible and synchronized with the existing region selector.

## Verification
Test exact match, mismatch, unknown metadata, cache separation, raw-versus-graded isolation, and UI parameter wiring.
