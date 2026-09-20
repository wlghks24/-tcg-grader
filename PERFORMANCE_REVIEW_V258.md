# Provider resilience and efficiency review v258

This pass models a large multidisciplinary review (data collection, parser safety, SRE, security, QA, tablet runtime, and market-data integrity). It is not a claim that 1,000 external people reviewed the repository.

## Verified gaps

1. Beckett maintenance mode caused the canonical grading page to be fetched again solely to prove maintenance status after the base watcher had already fetched it in the same transaction.
2. TAG's primary `/pages/pricing` page could return a structurally valid official page while the generic pricing parser produced zero verified service rows.
3. Company-level health could look healthy because a news/status source was reachable even while no fresh pricing source was available.

## Applied changes

- Per-transaction exact-URL request memoization; no persistent cache and no skipped scheduled checks.
- BGS maintenance status validation reuses the canonical grading response in the same run.
- Official TAG pricing fallback uses only `taggrading.com/collections/grading-services-official`, requires the final host to remain TAG, and requires multiple expected service tiers before promotion.
- Adds pricing-specific health metrics so provider reachability and fresh pricing availability are no longer conflated.
- Preserves fail-closed behavior: no community/search-result price promotion, no 403/429 bypass, no Beckett maintenance-price parsing.

## Remaining risks

- PSA programmatic official sources currently return HTTP 403 in automation. This remains degraded rather than being bypassed.
- Physical tablet Drive delivery remains pending until a matching receipt exists.
- Repository main branch protection is an administrative setting and should be enabled separately.
