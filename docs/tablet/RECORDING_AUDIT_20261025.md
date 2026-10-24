# Tablet recording audit — 2026-10-25

Input: user-provided 146.59 s, 1600x2560 tablet recording. Visual audit only; cannot infer HTTP logs, network latency, or measured frame-time.

## Reproduced on-screen symptoms
- At about 82 s, game = ALL, country = CN (China), type = ALL, status = ongoing/ended within five days, source = ALL.
- The UI says "중복 제외 278건 중 조건 일치 0건 · 현재 0건 표시" and "선택한 분류에서 확인된 정보가 없습니다."
- The same screen shows source coverage and SNS/Google candidate counts. Those are **not** evidence that a Chinese event passed the selected filters.
- Other screens include card price estimates, overseas listings, HOT entries, and grading-candidate counts; these are different evidence classes and must not be merged.

## Code inspection / root-cause candidates
- `update_promo_events.py:normalize_event_dates` derives date ranges from `name_native` and `name_ko`. Title-text date parsing is not by itself verified event-date provenance. Existing event date evidence gates need end-to-end inspection.
- `verified_collection_neural.py` contains a six-hour per-query deduplication gate and 1000/100-per-class activation requirements. Inspect actual 309 unverified legacy rows at runtime before claiming quarantine is enforced.
- `verified_collection_job_neural.py:ingest_verified_report` requires `postflight_monitor.results`; inspect completed job identity, per-file postflight, and six-hour independent-window behavior before admitting additional 400 samples.
- `china_official_catalog_v571.py` is an official-only Pokémon BOX discovery path. It cannot alone populate all China card/event/HOT/market sections.

## Mandatory acceptance checks (not yet passed)
1. CN selected with ALL game: show verified CN-S/CN-T catalog rows when present, without turning catalog rows into HOT or trade prices.
2. If zero matches, show total CN source coverage, filtered-out counts by status/time/type, and last successful China fetch separately.
3. Distinguish publication date from event start/end and require a linked official source plus explicit event-date evidence before confirmed status.
4. Quarantine unverified Query history; dedup verified observations; reject unfinished/non-postflight Job rows; preserve image grading hold.
5. Test mocked 200/404/429/500/503/timeout; enforce retry budgets and preserve last-good data.
6. Compare collection duration, peak memory, and UI responsiveness with reproducible before/after measurements.

**Status:** observational audit; no production code patch, no CI pass, no tablet update. Preserve last-good `c5bf5608b87b19d72e5b9f73a3aa0a466230f397`.
