---
applyTo: "**"
---

# TCG Grader repository instructions

Use the project-local skills under `.agents/skills/` before modifying code.

Route work as follows:
- behavior/bug/refactor → `tcg-test-driven-regression`;
- failure or broken CI/runtime → `tcg-debug-recovery`;
- PR/merge review → `tcg-code-review`;
- external input/network/file/subprocess/dependency → `tcg-security-hardening`;
- latency/resource/concurrency/image-cost change → `tcg-performance-budget`;
- workflow/release/schedule/integrity change → `tcg-ci-release`;
- logging/diagnostics/recovery evidence → `tcg-observability`;
- OCR/card-image/grading/calibration → `tcg-vision-grading`.

Repository rules:
1. Inspect neighboring implementation, tests, workflows, and Graphify/code-map guidance before editing.
2. Use targeted tests → related regression → current/full runtime checks → output validation.
3. Do not weaken tests or fail-closed guards to make CI pass.
4. Keep TCG mutual-sync local-only; do not add cloud learning or cloud parallel learning unless the user explicitly reverses that requirement.
5. Do not invent prices, grades, market direction, source verification, physical tablet results, or Drive/device readback.
6. Autonomous code may select only existing allowlisted declarative capabilities; new source-level functionality requires normal branch/PR/CI review.
7. Preserve domain isolation and protected data boundaries. Do not exchange raw peer weights, grading calibration, secrets, or private runtime state.
8. Keep network and file input bounded and validated; respect HTTPS/source/rate-limit/retry/cooldown contracts.
9. For GitHub Actions use least privilege, pinned action SHAs, concurrency protection for mutating jobs, and no direct-main autonomous writes.
10. Before merge apply `tcg-code-review` and `tcg-ci-release`; required CI must be green.
