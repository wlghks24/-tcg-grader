# TCG Grader V666 | Official IDs · edition proof · real CI recovery · 120-point assessment

**As-of:** 2026-10-12 KST. **PR:** #651, feature branch `feat/v628-official-sealed-proof-20261012`. Draft and not merged into `main`. All added code uses free Python standard library, official links, and GitHub public-repo Actions; no paid API or auto-billing.

## 1. Retrospective: CI was running, but errors were hidden by incomplete run lookup

The prior helper `fetch_commit_workflow_runs` searches **pull_request events only**; it did not reveal the actual `push` runs. The GitHub Actions REST collection `/actions/runs?branch=...` verified more than 100 historical workflow runs on the feature branch and gave explicit logs.

**Root-cause fixes from real GitHub runner tracebacks:**

| Original defect | Real exception / downstream effect | Exact remediation |
|---|---|---|
| `execution/official_box_coverage_audit_v623.py` manufacturer host dict omitted **two commas** after Sorcery and CookieRun | Python `SyntaxError`, all unittest suites unable to import | Restore both commas; compile the imported audit in CI |
| `test_tcg_event_rss_v647.py` contained Japanese UTF-8 characters in a `b"""..."""` bytes literal | Python `SyntaxError: bytes can only contain ASCII literal characters` | UTF-8 encode the Unicode RSS fixture at runtime |
| `tcg_multi_source_queue_v639.py` `prepare()` iterated over the intake JSON **dictionary**, not `intake["records"]` | `TypeError: string indices must be integers` broke manual 1,014-task queue and staging tests | Explicitly unpack `reg, intake, official` and use `leads = intake["records"]` |
| `tcg_tcgdex_sets_v640.py` cached simplified schema with `card_count_total`, but cache loader called the *API-only* validator expecting `cardCount.total` | `load_cache()` returned `None` immediately after successful cache write | Rehydrate the API-shaped object from strict on-disk rows before normalizing, preserving fail-closed checks |
| `integrity_manifest.json` was stale after source edits | SHA256/byte-size mismatch in regression | Recompute verified UTF-8 SHA256 and bytes for all changed files, retest |
| GitHub hosted checkout v4 emitted Node20 EOL warnings | Action compatibility warning; no data claim involved | Upgrade to `actions/checkout@v5` (Node24-compatible) |

**Verified GitHub Actions success:** [run #38242065358](https://github.com/wlghks24/-tcg-grader/actions/runs/38242065358), `push` SHA `62bd4d55e1182b7251377492a228015fd06e81cd`: **107 Python unittest tests PASS**, Python compile PASS, SHA256 preflight PASS, JS syntax checks PASS. This is not equivalent to Lenovo physical-device or CodeQL security approval.

## 2. Authentic printed card IDs and market-specific pack integrity

Two further primary sources were checked and source-locked:

- hololive official English errata page: https://en.hololive-official-cardgame.com/rules/errata/ ; **8 number/name pairs**. `hEB01-010` Tokino Sora; `hBP05-004` Nekomata Okayu; `hBP05-087` Jailbird; `hBP05-082` Aki Rosenthal’s Axe; `hBP05-067` and `hBP05-063` both Shiranui Flare, distinct print numbers; `hBP05-051` Hiodoshi Ao; `hBP05-050` Fuwawa Abyssgard. **Errata numbers are not current uncorrected card text, card rarity, grading, or proof of specific US printing SKU.**
- Dragon Ball Super Fusion World English North America publisher product: https://www.dbs-cardgame.com/fw/en/products/01_400.html ; **3 number/name pairs** `FB10-001` Son Goku, `FB10-073` Boujack, `FB10-097` Cell. Product page confirms `FB10` US booster pack **12 physical cards + 1 digital code**. Japanese manufacturer page https://www.dbs-cardgame.com/fw/jp/products/01_400.html says **6 physical cards/pack** for Japan. This disparity is **not** automatically a box-size discrepancy. U.S. manufacturer BOX display pack count is still unverified and must not be filled by guessing 24.

These 11 new pairs join the earlier 3 (Digimon and ONE PIECE) for **14 official manufacturer-listed card number/name samples covering 4 of 30 games**. They do not establish 14 finished-market sales, 14 PSA-graded values, or complete manufacturer card lists.

New additive file `tcg_manufacturer_card_evidence_v666.json`, policy validator `tcg_manufacturer_card_overlay_v666.py`, and `tcg_country_pack_discrepancy_v666.json` add exact-name, source, locale, code, market and no-rarity / no-price / no-pull-odds protections. `tcg_card_trade_evidence_v660.py` stages these new card identities but **never** elevates user-supplied completed-sale claims to verified prices. `test_tcg_v666_card_locale_evidence.py` tests cross-country conflict, fake card fields and price staging.

**No full-text or image scraping added**: manufacturer websites may forbid bulk reuse; only small identification facts and official links are staged. This workflow does not promise commercial redistribution rights for third-party imagery/data.

## 3. Coverage retained, no fabricated BOX growth

| Objective evidence | Verified recorded sample |
|---|---|
| Games represented in registry | 30 |
| User-submitted unverified candidate product/HIT/promo strings | 338 |
| Research jobs (manually verifiable), 8 search links each | 1,014 |
| Official manufacturer product examples | 101 |
| Manufacturer **general sealed booster BOX** examples | 64 |
| Declared game×country scopes | 55 |
| Game×country scopes with ≥1 official ordinary BOX example | 36 |
| Unfilled official BOX example scopes | 19 |
| Official source-linked printed card number/name pairs | **14 across 4 games** |
| Proven real completed sales / trustworthy market price observations added | **0** |
| Real PSA/CGC/BGS/TAG grade outcomes measured | **0** |

*Do not read 36/55 as completeness of all historic and upcoming booster sets*. One example in a region is not full coverage, and some declared scopes are discontinued/historical (WIXOSS US). To reach **49 active scopes** with an official example, current minimum additional evidence is **13 scopes**, not 13 boxes total in the market.

## 4. Reviewer scorecard (editorial, not validated product-performance benchmark)

| Category | Max | Conservative provisional credit | Blocking evidence |
|---|---:|---:|---|
| Product/BOX official evidence coverage | 30 | 17 | 19 region gaps, no complete sealed catalog |
| Printed card ID/edition/HIT provenance | 20 | 5 | 4 games /14 IDs, partial edition ambiguity, no real hit-rate calibration |
| Completed-sale evidence and source-specific pricing | 20 | 0 | No externally proven real transactions |
| Cross-language regression and security CI | 25 | 22 | 107 real tests passed; CodeQL separate results needed |
| Lenovo Tablet app installation, 30+ minute soak, reboot, offline recovery | 15 | 0 | No device logs or repeatable physical verification |
| Free-only, privacy, licensing, safety | 10 | 8 | Zero paid dependencies in this patch; external commercial-use rights unknown |
| **Provisional sum** | **120** | **52** | **Not an approval; 100+ unmet** |

The score is a **transparent editorial assessment**, not a statistically calibrated metric or an assertion that original code reached 100+.

## 5. Next acceptance criteria

1. 13 further **active game×country** ordinary BOX manufacturer proofs (SKU, language, box pack count, per-pack card count, date, link); maintain `P0_DECLARED_BOX_GAP` priority and do not substitute retail listings for manufacturer facts.
2. Increase official card ID evidence toward 20+ separate games, ideally sufficient sets per game; never conflate promo-gift cards, card rarity, signed art, and sealed-box pull rates.
3. Collect bona fide completed transactions with product ID, date, currency, confirmed sold status, and shipping/fees; allow verified price index only after independent evidence, not seller asking price.
4. Run Python & JS GitHub Actions on the **latest HEAD**; execute CodeQL Python/JS; triage alerts. CodeQL is now configured via `.github/workflows/tcg-codeql-qa.yml` with official `github/codeql-action@v4`, subject to runner permission/execution success.
5. On Lenovo Tablet Termux, from exact feature checkout: `python tcg_free_preflight_v664.py --full`; inspect returned JSON, node availability, browser rendering, app cold startup, 30 min repeated tests, offline cache and reboot recovery. This assistant cannot access the device remotely.

**Release decision:** HOLD / DRAFT. Do not merge or auto-deploy until external device gates pass, regardless of standalone GitHub Actions success.
