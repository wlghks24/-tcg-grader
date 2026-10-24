# V656 collection continuity and fair account rotation

The official-account Google/Bing discovery path remains bounded to six accounts,
twelve queries and a six-hour slot, with existing provider cooldowns and exact
owner/game attribution checks. This follow-up changes two concrete failure paths.

## No permanently skipped accounts

The prior selector rotated group and account positions by the same slot. With
nine game/country groups and nine accounts per group, the matching periods could
permanently skip some accounts. The selector now builds one stable interleaved
account list and visits consecutive blocks. With an unchanged eligible registry,
every account is visited within `ceil(account_count / 6)` consecutive slots,
including arbitrary starting slots. Search budget and provider spacing stay the
same. This guarantees scheduling coverage, not search-index or event coverage.

## Preserve recent official identities through temporary source outages

A failed official registry page previously removed all of its automatically
verified accounts and then postponed registry refresh for a week. Now:

- A successful page without an old account still removes that automatic account.
- A failed page may retain only its own previously trusted identity, with a matching
  safe profile, original official evidence and timezone-aware verification within
  30 days. No inferred/new account is added by this fallback.
- The original `verified_at` is unchanged. Retained accounts carry a DEFERRED
  refresh marker and failed-refresh time; repeated outages do not extend their
  original verification age. Expired, future, unsafe and cross-game evidence is
  rejected. Existing manually reviewed accounts keep their existing policy.
- Fresh official rediscovery replaces a deferred record. A failed registry is
  eligible to retry after six hours, and one page exception does not cancel the
  other pages' successful discoveries.

These are identity continuity and scheduling repairs. Search hits still require
proper ownership/evidence, publication dates do not become event dates, and
missing events remain explicit gaps. No platform login bypass, API credential
creation, extra paid provider, runtime self-rewriting or automatic new-game
promotion is introduced.

Deterministic fixtures cover failed/successful/removed/expired identities, source
and profile mismatches, repeated outages, retry freshness, page exception
isolation, the 81-account starvation case and the current registry. Existing
V655 tests continue exercising Google/Bing requests, Instagram candidate
attribution, request limits and persisted cooldowns. Source/CI validation does not
claim physical tablet installation or unrestricted Instagram access.
