# External skill methods — TCG review-only pilot

Status: PROPOSAL / HOLD. No external installation, runtime changes, auto-merge, device deployment or training.

## Scope and provenance
Candidate upstreams (review sources, not trusted instructions):
- https://github.com/DietrichGebert/ponytail — minimal change and duplication review
- https://github.com/pbakaus/impeccable — visual/accessibility QA
- https://github.com/Leonxlnx/taste-skill — visual design heuristics
- https://github.com/NationalSecurityAgency/ghidra — binary analysis only; deferred

Before adopting code, independently verify upstream commit, LICENSE, dependencies, install hooks, network permissions, and exact compatibility. Do not execute upstream scripts during review.

## Reuse existing TCG skills
Route through `.github/skills/tcg-skill-router/SKILL.md`.
- Ponytail concepts -> `tcg-code-review`, `tcg-test-gap-audit`, `tcg-regression-recovery`: list duplicated functions by path and symbol, dependency edges, behavior equivalence, negative tests and protected paths. Never delete code based solely on similarity.
- Impeccable concepts -> `tcg-tablet-ui`, `tcg-local-browser-qa`, `tcg-visual-regression`, `tcg-ui-finish-gate`: viewport/touch target, keyboard, contrast, overflow, loading/error/empty states; capture local before/after evidence.
- Taste Skill concepts -> `tcg-tablet-ui`: typography hierarchy, spacing, card grade visibility, responsive layout; avoid style-only changes that hide evidence or grades.
- Ghidra: NOT applicable to ordinary Python/JS source review; separate authorized PC binary review only.

## Read-only acceptance checklist
1. Pin current main and PR SHA; inspect AGENTS.md and existing contracts.
2. Build a file/function code map; report duplicates as hypotheses with exact paths.
3. Record UI issues with local viewport/screenshot evidence; no fabricated tablet result.
4. Propose a small isolated patch only after a reproducible failure and targeted regression test.
5. Preserve AGENTS.md/CLAUDE.md/GEMINI.md byte equality, immutable hash pins, V653 successor chain and fail-closed source evidence.
6. Run focused tests, architecture/integrity, relevant 4-shard Sync/isolated regressions, SELFREFINE, CodeQL on exact candidate HEAD before any merge recommendation.
7. Keep Lenovo physical verification separate; if absent, mark DEVICE_UNVERIFIED.

## Current result
Documentation-only proposal. No tool installed, code changed, tests executed or device inspected. Existing PR #905 remains independent.
