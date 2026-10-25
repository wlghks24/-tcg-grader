# TCG optional Camofox public-page snapshot candidate — design review (2026-10-25)

## Scope and change discipline
- Status: **proposal only**, NOT activated. Existing collectors, Termux runtime, image training, tablet UI, CI/workflows, model promotion and `main` are unchanged.
- This is a self-contained `execution/` support module using Python standard library only; the upstream Node.js/Camoufox binary is **not** vendored, installed, started or added as a dependency.
- The tool may be tried **locally** after independent permission/site-policy checking. It must not be used to bypass login, CAPTCHA, 403/429, robots, bot blocks, subscription or rate limits.
- Must preserve: existing source registry, per-collector error domains, `canonical_key`, `lineage_key`, last-good and source freshness policy, game/language/printing/grade distinctions, WATCH -> review -> promoted process. The adapter deliberately produces no canonical/lineage proof and cannot promote data.

## Why not integrate directly into collection loops?
- [Repo rule: AGENTS.md](../../AGENTS.md): tablet/device runtime and browser QA remain local-only. No hosted browser farms or cloud control plane.
- [Collector resilience](../../.codex/skills/tcg-collector-resilience/SKILL.md): official/API/RSS first, isolated fallback, no retry on 403/429, quarantine partial data.
- Browser snapshot is **not** reliable verification of original seller/issuer, card language, value, official source, product identity or completed sales. Provenance cannot be inherited from fallback.
- Termux Android direct binary compatibility is unknown. Aarch64 **Linux** binaries are not equivalent to Android/Termux binaries.

## Interface
`execution/camofox_public_adapter.py` provides `CamofoxPublicAdapter(enabled=False)` and `collect(url, source_policy_approved=False)`.

1. Disabled by default, no I/O at all when disabled.
2. Caller must independently review target site permission and provide a **specific** HTTPS allowed-host set.
3. Local server must bind `127.0.0.1:9377` and be protected by a strong `CAMOFOX_ACCESS_KEY`; no remote listener.
4. Bounded one-tab REST call to `/tabs` -> `/tabs/{id}/snapshot` -> close tab. No arbitrary `evaluate`, click, login, cookies, proxy or tracking.
5. Local API redirect entirely denied (no Bearer token forwarded). Requested and final public source hosts must match exactly and be on the approved list.
6. Reject partial, oversized, empty, malformed, restricted and failed navigation data; never retry permission failures.
7. Any candidate has `verified=false`, `official=false`, `production_promotion=false`. No automatic local-file write and no model training.
8. Snapshot text is hostile/untrusted data, never executable instructions. A separate existing trusted source verifier would be required before ingestion.

## Security/privacy setup for a *future* approved local pilot
- Do not run `npm install` on the Lenovo tablet until browser compatibility, storage footprint and permitted host tests are completed.
- The upstream server is optional infrastructure and its default bind can expose interfaces; **set** `CAMOFOX_BIND_HOST=127.0.0.1` and `CAMOFOX_ACCESS_KEY` to a strong runtime secret; reject non-loopback connections.
- Disable crash telemetry: `CAMOFOX_CRASH_REPORT_ENABLED=false`.
- Disable persistence, cookie import, VNC, and proxy features; never share account sessions or trading credentials.
- Prefer official API/RSS/static parser first, and run a single capture at a time only when authorized.
- Require pinned upstream version, dependency/SBOM review, code provenance, local measured RAM/storage/latency, last-good and rollback before deployment.

## Offline tests
Run from repository root:

`python -m unittest discover -s execution/tests -p test_camofox_public_adapter.py -v`

Tests use a local fake transport and one isolated loopback HTTP redirect fixture, never launch or install Camoufox. Passing tests verify **adapter contract only**. They do not prove a real browser, site compatibility, data truth, current CI or Lenovo physical device.

## Candidate promotion gates
- Verify upstream license including Camoufox browser and third-party components (server MIT, browser upstream MPL-2.0, additional notices).
- Verify source-specific permissions, data rights, timeout, 403/429 and no privacy or login collection.
- Confirm provider/collector ID isolation, lineage and game/set/variant boundaries.
- Run current-head focused + full regression CI; confirm integrity manifest/sync generation if adding watched live runtime paths.
- Physical Lenovo capture receipt required for **tablet compatible** claim.
- Until then: `HOLD`, leave feature flag off, do not ship or train from candidates.

Upstream source: https://github.com/jo-inc/camofox-browser (package `@askjo/camofox-browser` 1.18.1 at review time), based on https://github.com/daijro/camoufox. Note versions, links, and deployment guidance may change after review.
