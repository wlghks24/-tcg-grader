# TCG Grader: directive, orchestration and execution SOP (V546)

## Purpose and guardrails
Make TCG Grader changes measurable and repeatable while preserving the **existing** tablet runtime, card-grading calibration, market-source identity/freshness gates, and protected-main CI. This SOP is for development tasks; it does **not** grant autonomous source-code rewriting or device control.

## 1. Directive — define WHAT
- State a concrete feature/failure, scoped files, trusted input source, output and success/failure conditions.
- Start at `.github/skills/tcg-skill-router/SKILL.md` and select the relevant repository-owned review, market, tablet, security, regression and supply-chain skill. Preserve earlier historical TCG sync contracts.
- New card games enter WATCH, not automatic grading promotion. Grades, prices, transactions, stocks and releases require appropriate evidence.
- Run `python execution/architecture_audit.py --check` for the shared 3-layer guidance and credentials boundaries.

## 2. Orchestration — select and decide
Use the smallest already-existing deterministic tool before adding another one:

| Intent | Preferred existing entrypoint or check |
| --- | --- |
| Tablet update / start | `bash main update-now` then `bash main tablet-audit`; `bash main` only to start |
| Tablet read-only validation | `bash main verify`; `python tablet_runtime_manifest.py --check --compile` |
| Local TCG collection | `bash main collect` (no publishing); validate observed source dates |
| Candidate publish | `bash main publish` (protected PR flow, no direct main writes) |
| Main regressions | `python main_selfrefine_gate.py --self-test` and appropriate targeted tests |
| Repository integrity | `python repository_integrity_guard.py`, `python static_integrity_manifest.py --check` |
| Skill control plane | `python agent_skills_guard.py --check` |

Do not execute a production collection, send a PR, start the server or modify files merely by reading this SOP. User-authorized actions and current-head validation remain separate checks.

## 3. Execution — deterministic HOW
- Reuse existing tested modules in the repository root. The `execution/` directory holds *new supplemental helpers* (currently the read-only architecture audit), **not** a duplicate replacement for the running code.
- Standard library and explicit allowlists first; bounded retries/backoff for source errors, 403/429 are reported as degraded—not circumvented.
- Never execute an untrusted provider response, a generated shell command, or social-media text.
- Do not use automatic paid API calls or create cloud services. Local-only tablet/PC learning and QA are mandatory.
- Keep ephemeral intermediate files in ignored `.tmp/` or OS temporary directories. Keep `.env` and OAuth credentials out of version control. Do not commit trained-device memories or photos by default.

## 4. Verified self-annealing
1. **Observe:** capture log/trace, exact affected commit, provider link and observation timestamp without printing secrets.
2. **Classify:** identify code error, integrity mismatch, historical sync attribution, device limitation, API rate limit/403, or unverified/stale market evidence.
3. **Repair:** first look for an existing deterministic tool, then make a small bounded patch. Never weaken a guard to force a green result.
4. **Test:** run targeted behavior tests, current-head full CI, source integrity and Android/Termux regression where relevant.
5. **Conclude:** if any gate fails, leave the change unmerged or roll back; preserve last-good snapshot and report the blocker.
6. **Learn:** update this directive only with a **verified** failure mode and repair. Human review and commit traceability remain required.

### Evidence from 2026-10-09
A scheduled static refresh could validate data while GitHub Actions failed to create the protected PR with HTTP 403. This is **collected but not published**. The collection run's green status must not be described as an updated main/tablet price. Verify the PR, main commit, data source date, exact hashes and actual device installation separately. See issue #546.

## 5. Deliverables and release boundary
Current output is GitHub-reviewed source plus local tablet UI/JSON and optional user-directed export; do **not** impose Google Sheets/Slides or Drive on a local-only TCG product. Physical-device readback must be explicitly performed on the tablet. An agent must never claim it from passing GitHub Actions.
