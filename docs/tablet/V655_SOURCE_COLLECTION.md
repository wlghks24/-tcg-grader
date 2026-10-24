# V655 official-site and official-account collection

The normal `social_event_discovery.main()` and existing scheduled updater now run
an additional `official_account_search` collector. It uses the existing trusted
social registry, searches by exact handle + game + event/product terms, and
rotates game/country groups and accounts every six hours. Google News RSS and
Bing RSS are independent public discovery routes. Instagram, X, YouTube,
Facebook, TikTok and Twitch profiles are eligible when already verified in the
registry; this does not add or automatically trust new accounts.

## Limits and attribution

- At most six accounts and twelve requests per six-hour slot, with two provider
  workers and two-second spacing within each provider. The normal persisted
  channel status prevents the hourly watcher from repeating the same slot.
- Responses: eight candidates/query, 1 MB, eight-second timeout, HTTPS host
  validation and pre-follow redirect validation. HTML challenges and XML entity
  responses fail visibly.
- HTTP 403 stops that provider for 24 hours; HTTP 429 stops it for at least six
  hours and respects longer numeric Retry-After up to 24 hours. Cooldowns persist
  in `social_event_candidates.json` channel status. DNS/transport failures are
  DEGRADED, not successful collections.
- A query mentioning an official handle is not evidence of authorship. Generic
  Instagram `/p/` and `/reel/` URLs remain candidates until separately verified.
  Exact registered owner paths can identify official accounts. Shared publisher
  accounts also require game-name evidence in the result text.
- Search publication dates are not event dates. Existing lineage deduplication,
  canonical promo verification, WATCH/promotion and grading gates stay active.
- Existing optional Meta/X/CSE API integration remains available only when local
  credentials are configured. No credentials, login bypass, or new paid service
  is introduced. Search indexes do not guarantee complete Instagram coverage.

## Direct official pages

Official anchor discovery now reads image `alt`, `title` and accessible labels,
so image-only promo banners are no longer skipped. Generic navigation labels are
excluded and repeated links to one article produce one candidate. Request/result
limits stay bounded. The official Korean Pokemon `www` host is explicitly
allowed, matching the existing official apex route.

## Information board

Release and promo boards now expose game/country filters (including data-backed
additional games, GLOBAL and ASIA), visible selection/count summaries, panel-only
reset, and forty-row incremental display. Tab targets are allowlisted, and event
lifecycle uses sorted explicit dates. Native Android select popup placement is
controlled by Android; the attached screenshots alone do not establish a new
application routing failure.

## Validation boundary

Deterministic Python and Node tests exercise actual collector calls, both RSS
providers, rotation, persisted cooldowns, malformed responses, spoofed attribution,
shared publisher identity, banner extraction, filter intersections, pagination,
reset isolation and CSP hashes. This workspace's direct live probe returned DNS
lookup failures for Google/Bing. It cannot establish real collection yield.

No physical tablet installation, new neural training, rendered-after screenshot,
or measured tablet lag result is claimed. The V652 local UI review helper remains
the device verification route. Existing image collection caps are unchanged by
this event/source enhancement.
