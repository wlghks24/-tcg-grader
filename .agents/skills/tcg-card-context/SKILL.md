---
name: tcg-card-context
description: Resolve and present TCG game, set/block, edition/language, era/generation, card number, and release-era context without inventing unsupported generation labels.
version: "1.0.0"
---

# TCG Card Context

Use this skill whenever a card result must explain what game, set/block, printing era, generation, edition, or card number the card belongs to.

## Evidence order
1. Exact verified card number and set/product code.
2. Verified catalog identity for the same game and edition.
3. Copyright/production year as context only.
4. Regulation mark as context only unless a game-specific contract explicitly makes it a set identity.
5. Artwork similarity alone never establishes a generation or set.

## Game-specific display
- Pokémon: show a generation only when the existing generation runtime has supported evidence. Preserve fail-closed conflict/context-only behavior.
- ONE PIECE: show exact product/set family from a recognized prefix such as OP/ST/EB/PRB/P when present. Do not call this a numbered Pokémon-style generation.
- NARUTO and other games: show an exact observed set/product code when available; otherwise say the set/generation context is unverified.
- Never derive release year from copyright year alone.

## UI
Keep game, card name/number, edition/language, generation/set, grading result, and market evidence visually distinct. A user must be able to see which facts are exact, estimated, contextual, or unknown.

## Verification
Test known Pokémon generations, conflicts, context-only years, ONE PIECE exact prefixes, unknown/unsupported prefixes, missing card numbers, and non-Pokémon fail-closed labels.
