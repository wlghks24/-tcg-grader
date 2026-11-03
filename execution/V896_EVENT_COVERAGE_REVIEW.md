# V896 — registry-wide event discovery

Base source: `b8b0d645acf8ab15fef542e9b727b2674945b7c1`, existing PR #971. Status: **HOLD / device not run**.

## Confirmed gap and change

The legacy multi-route and social merge matrices cover three core games. The canonical promo updater already includes promoted-game official roots, but does not provide the same broad discovery path for WATCH games. V896 preserves both and adds a separate discovery lane derived from the validated registry: **30 games, 55 declared game/region pairs**, including WATCH. It does not claim worldwide TCG completeness, or enable grading/market activation for WATCH.

Movie/rerelease/encore, collaboration, promo/giveaway, pop-up/exhibition/cafe, event/tournament and release terms are searched in Korean, Japanese and English. Names come from registry canonical/local labels. Broad and exact registry-host searches share one fair persisted cursor. No new scheduler, service, dependency or account is added.

The explicit V889 startup adapter installs the lane before the existing hourly quick watcher starts. The normal updater invokes subprocesses, so its parent `core.update_cycle` is also wrapped: the existing manual POST/worker and regular update can collect the lane without depending on child-process monkeypatch inheritance. The previous worker and its request-origin checks remain authoritative. Existing entrypoints/boot files are unchanged.

## Boundaries and UI

- Maximum 12 requests / six cells per invocation, at least 30 minutes between active invocations, six-hour per-cell revisit interval. Provider 403/429 stops the pass and defers 24 hours. No bypass or rotating identity.
- A cooperative 45-second deadline is checked before each request and before/after streamed body reads; socket timeout is at most three seconds. This is not an OS hard-kill guarantee (DNS/OS calls can overshoot); late reads are never recorded as success.
- RSS maximum 400 KB, 12 hits/request; DTD/entities/private URLs rejected by existing HTTPS guard. Persisted file maximum 2 MB / 600 leads, atomic no-follow write and process lock.
- Search receipts are not event dates. Search country is not venue country or card edition. All leads remain `verified=false`, `region=UNKNOWN`, `card_reward_confirmed=false`, `date_status=UNCONFIRMED`, even on an exact registry host.
- UTM/mirror route duplicates use one game + canonical-source lineage. They never inflate independent corroboration.
- `/tablet-events-all` exposes all declared pairs, game/country filters and NOT_SEARCHED / STALE_SEARCH / SEARCH_FAILED / PARTIAL_SEARCH / SEARCHED_UNCONFIRMED. Existing confirmed-event lists remain available. New leads are deliberately not passed through the old core-only merge that would discard them.
- An empty result is not “no events”; attempted coverage is not confirmed coverage. Missing games/regions not declared in registry remain outside this lane until evidence review.

## External reference checks (2026-11-03 web review, not tablet collection)

Primary pages confirm that event/bonus collection needs broader game coverage and region-specific evidence. No third-party source code was copied.

- Pokémon: https://www.30th.pokemon-card.com/event/30thgym — official participation promo distribution spans 2026-09-16 through 2027-01-31.
- Weiß Schwarz: https://en.ws-tcg.com/events/8-race-wonder-campaign/ — eight shop-tournament participations July–December 2026, separate PR redemption conditions from November. Do not replace these conditions with a generic giveaway flag.
- Digimon: https://world.digimoncard.com/news/2026-dash-pack-cp.php and https://en.digimoncard.com/news/2026-dash-pack-cp.php — distinct regional pages describe 12-pack versus 10-pack purchase requirements. They must not be merged into one presumed universal condition.
- MTG: https://magic.wizards.com/en/news/announcements/secret-lair-corn-maze-superdrop — official cross-brand product announcement; collaboration vocabulary extends beyond the three core franchises.
- ONE PIECE FILM GOLD rerelease advertisement remains an unconfirmed recovery example here. A community search result is not proof of a current card bonus. Historical 2023 FILM RED encore bonuses are not 2026 GOLD evidence.

## Registry inventory

The following URLs are registry declarations, **not 30 fresh network verifications**. Every row is included in the planner without hand-coded game selection.

| Game ID | Registry state | Declared search regions | Registry official source |
| --- | --- | --- | --- |
| pokemon | core | KR, JP, US | https://www.pokemon.com/us/pokemon-tcg/ |
| onepiece | core | KR, JP, US | https://en.onepiece-cardgame.com/products/ |
| naruto | core | KR, JP, US | https://www.naruto-cardgame.com/asia-en/ |
| gundam | promoted | JP, US | https://www.gundam-gcg.com/en/products/ |
| unionarena | promoted | JP, US | https://www.unionarena-tcg.com/en/products/ |
| dbsfw | promoted | JP, US | https://www.dbs-cardgame.com/fw/en/products/ |
| lorcana | promoted | US | https://www.disneylorcana.com/en-US/ |
| swu | promoted | US | https://starwarsunlimited.com/ |
| riftbound | promoted | KR, US | https://playriftbound.com/en-us/ |
| mtg | promoted | JP, US | https://magic.wizards.com/en/products |
| yugioh | promoted | JP, US | https://www.yugioh-card.com/en/products/index.html |
| digimon | promoted | JP, US | https://world.digimoncard.com/products/ |
| flesh-and-blood | watch | JP, US | https://fabtcg.com/en/ |
| weiss-schwarz | watch | JP, US | https://en.ws-tcg.com/products/ |
| cardfight-vanguard | watch | JP, US | https://en.cf-vanguard.com/products/ |
| hololive-ocg | watch | JP, US | https://hololive-official-cardgame.com/en/products/ |
| shadowverse-evolve | watch | JP, US | https://en.shadowverse-evolve.com/products/ |
| grand-archive | watch | KR, JP, US | https://www.gatcg.com/article/products |
| final-fantasy-tcg | watch | JP, US | https://fftcg.square-enix-games.com/na |
| sorcery-contested-realm | watch | US | https://sorcerytcg.com/ |
| godzilla-card-game | watch | JP, US | https://en.godzilla-cardgame.com/products/ |
| palworld-ocg | watch | JP, US | https://en.palworld-official-cardgame.com/ |
| cyberpunk-tcg | watch | US | https://cyberpunktcg.com/ |
| elestrals | watch | US | https://www.elestrals.com/news/play-divine-champions-snowshade-early-at-prerelease-events |
| rush-of-ikorr | watch | US | https://my.upperdeck.com/public/roi/cards |
| cookierun-braverse | watch | KR, US | https://cookierunbraverse.com/en/notice/all |
| universus | watch | US | https://uvsgames.com/universus/ |
| alpha-clash | watch | US | https://alphaclashtcg.com/organized-play |
| metazoo | watch | US | https://www.metazootcg.com/ |
| wixoss | watch | JP, US | https://www.takaratomy.co.jp/products/wixoss/event/wixoss_party/ |

## Verification

- Local Python 3.12.14: **25 deterministic tests passed**; actual registry, fair full-matrix rotation, persistent cursor, max requests, interval deferral, malformed nested state preservation, source lineage, WATCH isolation, country filtering, escaped external text, movie without card bonus, 403/429, deadline/late EOF and parent-updater composition.
- Runtime module / new tests compile. One additional HTTP route integration test is registered in the existing full CI suite; it was not run locally because this workspace contains selected source files, not a complete checkout.
- Independent code review reproduced two defects (nested state written before report validation; second request after deadline) and a late EOF boundary. All have explicit regression tests and fixes.
- Code Preflight v2 scans selected restored source only; HIGH/MEDIUM zero at the earlier scan. Missing optional Ruff/Bandit/Gitleaks/actionlint and incomplete repository scope keep HOLD. Fresh final scan and current-head CI are reported separately.
- No live collector, tablet UI/browser, device install, training, performance benchmark or full source audit was run here. Main is unchanged; no merge/install performed. The previous V895 head's CI result is separate evidence, not a V896 pass.
