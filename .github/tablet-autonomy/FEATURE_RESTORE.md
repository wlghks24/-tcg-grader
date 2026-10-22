# Rebuilt tablet-private feature bundle — code review checkpoint

Base: main 6ce814e70ecbeca7ee2c659e6bb7c479f2d8bccc.
The user supplied 16 modified source originals and five image modules. After the two original private bridge modules could not be recovered, the user explicitly requested reimplementation instead of further archive requests. This bundle rebuilds those entrypoints from inspected Python/JS call contracts; it does not claim recovery of the unknown original implementations.

## Result
- tablet_catalog_auto_reflect_v43.py and tablet_collection_image_bridge_v42.py delegate to new execution/tablet_catalog_bridge.py, preserving the existing read_live/safe_priority/safe_cycle/analyze interfaces and v46 UI response shape.
- Unique exact code + game + edition + kind is required for a metadata link. Name similarity, code prefix overlap, competing photos/sources and edition/kind conflicts do not establish identity. File presence/size is checked in reports; SHA-256/MIME is verified on image delivery.
- Existing release/watch/market observations enrich matching image records in derived API results, retaining source lineage and unknown facts. Missing images/metadata create a bounded private gap queue and collection priorities. Existing collectors remain responsible for external facts; no arbitrary source fetching, fabricated pricing, stock, grades, ownership or training labels.
- Images, indexes, collection state and gap queues remain in tablet Pictures/TCG_Card_Images outside Git. No image binaries are in this source change. Existing manual/original photos are not rewritten. Automatic new photos use pixel/dimension-verified lossless WebP only when smaller.
- Conservative rolling collection ceilings: 24 images/run, 96/24h overall, 24/provider/24h; 6h scheduler; requests/bytes/runtime bounded, 2s request spacing, 403/429 cooldown and Retry-After. Limits are internal budgets, not guaranteed provider throughput.
- Unified KR/JP/US/CN controls include Chinese edition grouping while retaining CN-S/CN-T identity. BOX photo rendering now honors the selected game. Official Chinese product candidates are source observations, not verified prices or holdings.
- Preserve 8 categories and 18 primary adaptive actions. Add BOX image management access; keep advanced actions searchable. Fix queued details toggle resetting a just-selected view, repeat management clicks closing a target, and stale competing scroll callbacks. Compact focused detail mode retains back/collapse controls.
- Static navigation audit is part of runtime preflight. Its inventory is not a claim that every button was physically executed. Existing verified local training and last-good gates remain unchanged.
- Safe updater archives reviewed untracked source collisions before adopting the new tracked modules and restores them if fast-forward fails. Runtime JSON, including catalog_image_manifest.json, is retained. Unknown source changes/collisions remain protected by fail-closed/native Git checks.

## Evidence
Focused unit/DOM regressions include identities, ambiguous/missing/stale data, source failure, private storage, lossless byte preservation, quotas/backoff, navigation races, and Git source-adoption rollback. Native runtime manifest now compiles the full bundle without the two formerly missing dependencies.
1000325303.mp4/5308.mp4/5311.mp4 contain historical work records; 1000325312.mp4 shows the current app navigation. Their visible reports do not substitute for current code/device validation. 1000325257.mp4 was unavailable. Existing 47/30 image inventory figures are not summed without deduplication.
Local Chromium binaries are unavailable; rendered UI and physical Lenovo runtime/collection/training/reboot remain unverified. No tablet data/source was remotely changed here. Promotion requires the exact successor proof and current-head CI; actual tablet verification follows installation.
