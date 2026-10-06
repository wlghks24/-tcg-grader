# TCG Grader project skills

These repository-local skills adapt public engineering-skill patterns to the TCG Grader codebase. They are intentionally project-specific and do not copy external skill packs verbatim.

## Skill routing

- `tcg-test-driven-regression`: logic changes, bug fixes, behavior changes.
- `tcg-debug-recovery`: failures, flaky tests, broken workflows, runtime incidents.
- `tcg-code-review`: every PR before merge.
- `tcg-security-hardening`: external data, file input, subprocesses, network calls, secrets, dependencies.
- `tcg-performance-budget`: latency, memory, CPU/GPU, tablet/Windows resource use.
- `tcg-ci-release`: workflows, branch/PR gates, release and rollback.
- `tcg-observability`: logs, diagnostics, error taxonomy, recovery evidence.
- `tcg-vision-grading`: OCR, card boundaries, 1-4-8 image analysis, grader prediction/calibration.

## Required verification chain

For code changes, use the narrowest relevant test first, then related regression, then repository-wide/current-runtime gates, then actual output validation. Do not weaken a test to make a change pass.

## Safety boundaries

TCG mutual-sync remains local-only unless the user explicitly reverses that requirement. Never invent grades, prices, market direction, physical-device results, or source verification. New source-level functionality goes through normal branch/PR/CI review.

## Source inspiration

Structure and workflow ideas were reviewed from public Agent Skills repositories, especially addyosmani/agent-skills and anthropics/skills. The content here is rewritten for this repository and its existing fail-closed controls.
