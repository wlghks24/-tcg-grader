# China coverage + collector resilience: pre-merge acceptance gates

Baseline last-good: c5bf5608b87b19d72e5b9f73a3aa0a466230f397. This branch MUST NOT be deployed to tablets before CI, review, and physical verification.

## P0 source recovery
- Retry only transient 429/500/502/503/504 and timeouts with bounded exponential backoff, jitter, and a total request budget; honor valid Retry-After with an upper bound.
- Do not retry 404 in a tight loop; queue official URL migration checks.
- Preserve last verified data and isolate failed sources. No security bypass, proxy rotation, or 403 circumvention.
- Test 200, 404, 429, 500, 503, timeouts, malformed Retry-After, exhaustion, cancellation, and budget limits with mocked HTTP.

## P0 provenance and training
- Publication date != event date; without explicit event-date evidence keep candidate pending, not confirmed.
- Query: 309 legacy unverified records remain excluded; independent, deduplicated, pre-outcome feature records only; minimum 1000 and 100 positive/100 negative.
- Job: minimum 1000 independent verified postflight records; current 600, remaining 400; preserve mandatory collectors.
- Image grading: require official certificate bound to reviewed raw photos; do not change production model while missing.

## P1 China coverage
- Keep ALL/KR/JP/US/CN single combined selector; internally preserve CN-S and CN-T and HK/TW locale.
- Official CN-S/CN-T catalog-only entries must appear as catalog, never as verified market prices, completed sales, HOT signals, or owned inventory.
- Identify missing CN-S/CN-T Pokémon, One Piece, Naruto card and BOX official feeds independently. No cross-language fallback, guessed product identities, invented release dates or prices.
- Test catalog ingestion, country navigation, card/BOX search, zero-result explanation, de-duplication, and evidence gates.

## P2 performance and release
- Record collection duration, memory peak, UI interaction latency on the same hardware and workload before/after.
- Run Python syntax and focused tests, country navigation JS tests, full regression, CI/CodeQL and inspect diff/code map.
- Merge only after all mandatory checks pass; preserve last-good and rollback instructions.

This document is an acceptance plan, NOT implementation or test-pass evidence.
