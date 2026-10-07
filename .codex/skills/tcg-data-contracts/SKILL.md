---
name: tcg-data-contracts
description: Define and enforce deterministic schemas and compatibility contracts for TCG registry, market, grading, sync, learning, and tablet runtime data.
version: "1.0.0"
---

# TCG Grader Data Contracts

Use this skill whenever a JSON/JSONL/CSV/runtime state shape changes or data crosses collector, grading, market, UI, Tablet GPT, or GitHub validation boundaries.

## Contract rules
1. Write the producer and consumer contract before changing fields.
2. Distinguish required, optional, nullable, enumerated, bounded numeric, timestamp, URL, and opaque-ID fields.
3. Unknown or malformed trusted-state fields fail closed unless an explicit compatibility rule permits them.
4. Version schemas when semantics change; do not silently repurpose an existing field.
5. Keep runtime state separate from source configuration and immutable evidence.
6. Validate URLs, finite numbers, timestamps/timezones, collection limits, IDs, path containment, and maximum payload size at the boundary.
7. Preserve provenance and freshness through transforms; never strip lineage merely to satisfy a downstream schema.
8. Migration must be deterministic and test old→new, new→new, missing fields, extra fields, corrupted data, and rollback.
9. Writers use atomic replacement where the repository already requires it.
10. Consumers must not infer verified facts from field presence alone.

## Compatibility gate
A schema change is complete only when focused producer tests, consumer tests, persisted-state migration tests, runtime manifest/integrity checks, and actual representative output all pass.
