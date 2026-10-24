# PR #814 — immutable successor recovery worksheet (HOLD)

Status: `CANDIDATE_SPEC_ONLY`; **not** a verified V665 successor, PR approval, training approval, or tablet deployment receipt.

## Exact revisions reviewed
- Protected last-good main: `c5bf5608b87b19d72e5b9f73a3aa0a466230f397`.
- PR #814 functional candidate inspected: `48c3481915342e59bca91a306be1778cf24d9352`.
- PR ref: `fix/china-coverage-safety-review-20261025`; do not write to `main` or merge this draft without fresh full-head CI.

## Root-cause groups (observed, not speculative)
1. `V653_PROOF.reviewed_sha256['update_promo_events.py']`: historical approved `02959b8c5868ea6c6f188b8a8ac13614d17633d4f6e858bc46d0e5629558a024` (73,351 bytes), PR current `86c6fca020d22d92b176d26199fd4543bdc1294a6e851805caf199d95fc6e843` (73,132 bytes). The title-date verification change is real; NEVER rewrite V653 history to make hashes match.
2. `V645_FEATURE_PROOF.reviewed_sha256['tcg_reliability/china_official_catalog_v571.py']`: historical approved `34457a1d6baeabb9d33dc6b5084f5d96786e427da331f82b15ce441985aef192` (6,947 bytes), PR current `5321afb65d990ccdab8ba300fa3ea3181a2e32742a2b78f9dc66e8ef8a5f3cd2` (8,509 bytes). The network retry change is real; NEVER replace V645's pin.
3. All four `Sync generations` CI shards and all four isolated root-regression shards fail at PR head; the `Exhaustive SELFREFINE` failure is downstream of failed root shards. Multiple older generations (V426/V427 watched paths, V469/V478 BOX UI, V471 `main`, V566 app shell) are implicated in the cascade. No single-file change has been proven to clear every failure.
4. `Repository Integrity Guard`, `Main SELFREFINE`, `Deep SELFREFINE`, `CodeQL` succeeded on PR head. This is **not** a release pass.

## Required successor approach (do not bypass)
1. Freeze and inspect the **exact** functional candidate and `git diff --name-status MAIN_SHA..CANDIDATE_SHA`. Classify the two modified watched runtime paths, added offline tests, new China adapter, new workflow, documentation, and `integrity_manifest.json` independently.
2. Create a **new append-only** successor proof; do not edit old V645/V653 source SHA, old candidate commits, or older test expectations. Its exact `base_main_sha`, `candidate_commit`, watched-path set, predecessor and current SHA/byte pairs, immutable Git ancestry, and auxiliary paths must be validated.
3. New sync contract, delta, receiver receipt and test must be mutually digest-consistent, and `prior_contract`, `prior_delta_snapshot`, `current_required_lesson_count` must match the latest verified generation. Do not assert any physically observed tablet receipt from GitHub CI.
4. When delegating older generations, require strict newer candidate ancestry and matching **current** bytes, not only matching immutable historical `git show`. Altering a current watched file after evidence generation must cause FAIL. Preserve detection of unreviewed changes and earlier changes that predate the candidate's base.
5. Run new targeted proof tests plus existing V645/V653, V426/V427, V469/V471/V478/V566, current `Sync generations (0..3)`, root shards, `Exhaustive SELFREFINE`, Repository Integrity, CodeQL and branch-head status. Only all required PASS at one identical HEAD may enter merge review.
6. Lenovo physical-tablet runtime, source/date provenance, CN-S/CN-T coverage, Query/Job independent labels, source 429/5xx budgets, and rollback must be verified separately before deployment.

## Release/automation limits
- Never delete skipped/failed checks, weaken allowlists or broaden historical scopes to suppress red CI.
- Do not merge or push to `main`; do not auto-install on Lenovo; preserve last-good and locally stored images/learning data.
- No hosted agents, free-to-paid cloud upgrade, new paid API, or unreviewed source auto-generation.
- This file is a review artifact, **not** the missing successor implementation. The PR remains HOLD until steps above are actually implemented and pass.
