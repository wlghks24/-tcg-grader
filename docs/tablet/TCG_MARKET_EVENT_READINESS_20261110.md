# 태블릿 카드 AI · 시장·이벤트·등급·UI 우선 검수 (2026-11-10 KST)

## Evidence boundary

- Examined protected `main` at `c7486f46997f4034e41d7f18d5a2f5e94c4de4d8`. This is a scoped current-source review, **not** full historical code verification.
- `market_prices.json`: 38 price items (13 HIT / 25 BOX), all 38 only have `source_date` and none has a separate `market_observed_at`. Snapshot updated 2026-10-08.
- `exchange_rates.json`: `source_timestamp=2026-10-08T00:00:00+00:00`; cannot be presented as current KRW conversion on 2026-11-10.
- `promo_events.json`: 29 items; 9 `movie`, 8 tracking-only movie entries; 2 records have a past `end_date` while `status` still says `진행 중`, and 7 still say `lifecycle=current` after their `archive_on`.
- GitHub Actions: 2026-11-10 Exhaustive SELFREFINE shards failed on unreviewed V426 watched paths; package workflow failed collection verification with unhealthy PSA/BGS sources. Individual successes are not whole-release approval.
- Physical Lenovo verification: **NOT RUN**. Source/CI verification cannot be called installation.

## Cross-perspective review (engineering priority scores, not model quality or measured accuracy)

Score is **a triage decision** from 1 (low) to 5 (highest urgency), not evidence that an algorithm passed tests.

| Perspective | Observed gap | Priority | Smallest safe next change | Acceptance test |
| --- | --- | ---: | --- | --- |
| Market evidence / HOT | Source date substitutes for direct observation; stale cards/boxes can look current | 5/5 | Show FRESH/AGING/STALE/UNKNOWN and sale-vs-asking tier, never manufacture a trend | Future/stale/source-only synthetic cases; current provider evidence |
| FX / KRW | October 8 USD/JPY source is stale | 5/5 | Keep last-good reference but block current KRW conversions until a fresh proven quote | Cross-quote provenance and 72h fail-closed regression |
| Event / collaborations / films | Expired events still active, movie-watch entries not announcements | 4/5 | Reconcile lifecycle by source date; show film schedule as unconfirmed until publisher/KOBIS proof | Expired-event, overdue-archive, watch-only tests |
| UI / tablet | V881 market hub renders display price without individual freshness badge | 4/5 | Separate exact-reviewed successor for UI, with tablet-width and keyboard/touch tests | DOM, date, verified-identity, accessibility checks |
| Grade / learning | Runtime exists but no new verified photo calibration or accuracy measurement in this audit | 5/5 | Keep grading/learning gates closed; obtain approved photographed labels before confidence score | Calibration, holdout, error matrix, false-positive/negative |
| Android / release | Earlier successor and package CI failures; device not observed | 5/5 | Repair successor ancestry on separate PR, green exact-head gates, deploy with local rollback and SHA readback | All CI plus explicit installed SHA and restart/readback |

## Delivered in this review branch

`execution/market_event_readiness_audit.py` is **read-only**, local, standard-library-only, and bounded. It checks:
- FX origin, timestamp validity and stale/future windows without inventing exchange rates
- Identity-separated HIT/BOX sources, direct market-observation freshness, HTTPS source and link status
- Expired-but-active event records and overdue archive status
- Unconfirmed movie watch counts
- Honest `NOT_MEASURED` grading and `physical_tablet_verified=false` / `auto_install_allowed=false`

Run from repository root:

```sh
python execution/market_event_readiness_audit.py
python -m unittest -v execution.tests.test_market_event_readiness_audit
```

Six isolated, synthetic-only regression cases passed in the coding environment. This is **not** a pass report from GitHub Actions or Lenovo; a separate PR/current-HEAD validation is still required.

## Required next gates (HOLD)

1. **P0 release/sync**: explain every unreviewed V426 watched path using an exact SHA successor contract, not test downgrades; eliminate the four Exhaustive shard failures.
2. **P1 evidence**: collect actual current sources at a lawful rate; independently verify timestamp, set, language, edition, printing, condition, grading state and completed-sale vs listing status. Recheck FX and event lifecycles.
3. **P1 UI**: introduce stale/unknown badges and KRW conversion availability into the active application through a separately reviewed immutable successor, rather than editing V881's pinned byte contract in place.
4. **P1 model**: no re-training or numeric grading accuracy without reviewed real labels and holdout results. HOT projected prices should be bounded scenarios with provenance and no profit claims.
5. **P0 deployment**: require exact-head targeted/whole CI, source integrity, CodeQL, Sync four shards, Exhaustive four shards, device preflight, backup/rollback, then local Termux update; verify deployed SHA and UI on-device. No remote installation is asserted.

No pricing snapshots, approved grading model, protected `main`, local card photos or Termux device settings were changed by this candidate.

## Related existing draft work — review, do not duplicate or merge out of order

The following are **pre-existing draft/HOLD implementations**, not merged or installed. They are stacked on different exact base SHAs; do not cherry-pick or merge blindly:

- #1096 (V983): publish-gate event lifecycle and freshness, including regression.
- #1098 / #1100 / #1102 (V984/V986/V988): HOT completed-sale evidence, BOX product identity and seller URL-ID verification.
- #1101 (V987): stricter USD/JPY quote and source parsing. **Does not refresh October live rates.**
- #1104 (V990): deduplicate confirmed sales by sale ID and quarantine conflicting prices.
- #1105 / #1106 (V991/V992): unannounced film/collaboration expiry and matching browser UI.
- #1112 (V995/V996): historical exact-SHA successor repairs and CI lineage; still unresolved full-head CI.
- #1113: independent read-only diagnostic candidate in this branch.

Recommended review order: resolve exact-head predecessor and successor chain -> verify relevant feature PR against that exact integration HEAD -> validate data refresh/grade labels -> full integrity/CodeQL/Sync/Exhaustive -> physical Lenovo backup, approved install, and SHA readback. This audit does not amend or approve the other draft PRs.
