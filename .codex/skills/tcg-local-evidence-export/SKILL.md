---
name: tcg-local-evidence-export
description: Export TCG measurement and market evidence to local CSV or JSON safely, preserving provenance and user ownership without adding cloud storage, remote upload, or hidden synchronization.
version: "1.0.0"
---

# TCG Local Evidence Export

Use when adding CSV/JSON export, backups, handoff files, or evidence snapshots from tablet/browser surfaces.

## Local-only boundary
Exports are created on the user's device/browser. Do not add cloud upload, Drive sync, analytics upload, hosted storage, or background transfer.

## Export contract
1. Include a generated timestamp plus card identity fields available on screen.
2. Preserve recommendation basis, confidence, freshness, source name, source price, observation date/age, evidence class, whether the source contributes to the recommendation, and source URL when public.
3. Keep missing values blank or explicit; never manufacture a value for export completeness.
4. Sanitize filenames and cap user-derived filename length.
5. CSV must be spreadsheet-friendly UTF-8 and quote fields safely.
6. JSON must preserve nested source/grade evidence needed for later audit.
7. Never export secrets, API tokens, local absolute paths, cookies, private runtime memory, or hidden credentials.
8. Export does not count as backup until the user actually saves the file; do not claim physical-device readback without evidence.

## Verification
Test presence of local download actions, safe escaping, evidence fields, absence of network upload code, and continued tablet/PWA runtime compatibility.
