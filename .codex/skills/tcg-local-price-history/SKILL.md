---
name: tcg-local-price-history
description: Maintain bounded local-only TCG price-observation history and recent measurement shortcuts without calling a local snapshot an official sale history.
version: "1.0.0"
---

# TCG Local Price History

Use this skill for local price snapshots, recent-card history, trend summaries, and browser-side persistence.

## Local-only boundary
1. Store snapshots only on the current device/browser unless the user explicitly requests another destination.
2. Do not add cloud synchronization, analytics upload, background telemetry, or hidden network transfer.
3. Bound storage by identity/day and cap total rows.
4. Store compact fields only: exact query/identity context, date/time, condition, printing, edition, recommendation, source count, confidence, and freshness.
5. Never store raw card photos, credentials, API keys, cookies, or absolute local paths in browser history.

## Interpretation
Local lookup history is not transaction history. Label it clearly as values observed by this device. A 7D/30D change is computed only when an older local snapshot exists; otherwise show that data is still accumulating.

## UX
Recent measurements should be quick shortcuts, not hidden learning labels. Reopening a recent item may refill filters and rerun the normal verified evidence pipeline.

## Verification
Test bounded storage, same-day replacement, local-only APIs, clear-history behavior, missing baseline behavior, and no upload primitives.
