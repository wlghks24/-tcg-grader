---
name: tcg-pwa-runtime-audit
description: Audit the TCG Grader local PWA for service-worker cache compatibility, offline/app-shell delivery, stale assets, install/update behavior, local-server routing, and low-resource tablet performance without cloud services.
version: "1.0.0"
---

# TCG PWA Runtime Audit

Use for service-worker, manifest, cached asset, local server, installability, stale UI, or update-delivery changes.

## Local-only boundary
1. The production runtime is the local tablet/app server. Do not introduce cloud hosting, cloud sync, cloud rendering, or cloud compute as a requirement.
2. GitHub remains source/PR/CI infrastructure only; it is not part of the tablet live data path.
3. Prefer deterministic repository checks plus local browser/application inspection.

## Audit checklist
1. Confirm every required UI/runtime asset is actually served by the local server.
2. Confirm service-worker caching includes newly required static assets without silently changing a compatibility ABI.
3. Preserve the current cache ABI unless a deliberate migration has its own regression and rollback plan.
4. Verify activation cleans obsolete caches without deleting currently required offline assets.
5. Verify update flow cannot leave HTML/JS/CSS on incompatible generations.
6. Check manifest/install metadata and local URL scope.
7. Check offline or network-failure behavior only for features designed to support it; live market data must remain honestly unavailable/stale rather than fabricated.
8. Bound cache growth and avoid precaching large or frequently changing market/image data.
9. Verify stale cached UI can recover after the repository update command and app reload.
10. Check that cache or service-worker failures do not disable local update/status/audit commands.

## Performance
Measure locally when possible: startup time, JS/CSS payload, cache size, layout stability, and main-thread responsiveness. Treat unmeasured performance claims as hypotheses.
