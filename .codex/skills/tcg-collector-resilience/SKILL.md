---
name: tcg-collector-resilience
description: Design and review resilient TCG web and market collectors with bounded queues, provenance, rate limits, retries, differential collection, deduplication, and fail-closed fallback behavior.
version: "1.0.0"
---

# TCG Grader Collector Resilience

Use this skill for official sites, retailers, social channels, market sources, release/promo feeds, and cross-region KR/JP/US collectors.

## Collection contract
1. Prefer official/API/RSS sources before generic search or browser fallback.
2. Every observation records source URL, source class, region, collection time, lineage, verification status, and freshness.
3. Queue work with explicit per-source budgets. Do not fan out without bounds.
4. Respect rate limits and Retry-After. 401/403/451 are not permission to bypass access controls.
5. Retry only transient classes such as timeout, DNS, connection reset, or eligible 5xx. Keep retry count and backoff bounded.
6. Deduplicate mirrors/fallbacks by lineage before counting independent corroboration.
7. Use differential collection where possible: compare against last verified snapshot and prioritize changed/new records.
8. Parser/schema failures quarantine the new observation; they do not overwrite last-known-good data.
9. A fallback source may restore availability but does not inherit the trust grade of the failed primary.
10. Output validation includes empty, duplicate, stale, malformed, oversized, reordered, and partial responses.

## Learning boundary
Collector success/failure statistics may tune bounded timeout/order preferences. They must not learn credentials, bypass methods, source truth, market direction, or executable code.
