---
name: tcg-python-quality
description: Implement and refactor Python in TCG Grader with bounded runtime behavior, safe state handling, Termux compatibility, deterministic tests, and minimal dependency growth.
version: "1.0.0"
---

# TCG Grader Python Quality

## Runtime baseline
- Keep Python compatible with the repository's declared Android/Termux baseline.
- Prefer the standard library when it is sufficient.
- Do not add a mandatory dependency only to simplify a small helper.
- Treat network, subprocess, filesystem, JSON, and model-state input as fallible.

## State and file safety
- Use existing `safe_runtime` primitives for atomic JSON writes, bounded reads, and locking where applicable.
- Reject malformed/non-finite model values and corrupted state; fail closed instead of silently resetting a trusted champion.
- Keep device-local learning/cache/state in the existing ignored paths. Never turn runtime state into repository source truth.
- Avoid unsafe symlink following, path traversal, and partially-written state.

## Control flow
- Bound retries, history, candidate counts, file sizes, concurrency, and timeouts.
- Avoid catch-all exception swallowing. Report a stable error class without leaking secrets.
- Do not use `eval`, `exec`, generated shell commands, or learned text as executable code.
- Keep mutation behind existing verification/audit/resource gates.

## Tests
- Add deterministic unit tests for new logic.
- Include malformed, empty, duplicate, stale, and boundary-value cases.
- Reuse existing project fixtures and contracts before inventing parallel abstractions.
- Run the owning targeted test first, then the required project guards for the touched boundary.
