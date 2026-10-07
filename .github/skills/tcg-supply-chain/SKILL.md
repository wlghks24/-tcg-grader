---
name: tcg-supply-chain
description: 'Protect TCG Grader dependency, GitHub Actions, generated evidence, integrity manifests, agent skills, and runtime packaging. Use when adding dependencies, workflows, external skills/tools, generated contracts, or files shipped to the tablet.'
---

# Supply Chain and Provenance

## Before adding external code or skills
- Verify repository identity, license, maintenance status, and exact files needed.
- Prefer adapting a documented pattern over importing a large runtime dependency.
- Do not copy code with incompatible or unclear licensing.
- Minimize transitive dependencies.

## Repository integrity
- Track security-critical runtime and verification files in `integrity_manifest.json`.
- Recompute exact UTF-8 bytes and SHA-256 after changes.
- Keep generated sync contracts/deltas/receipts internally consistent.
- Preserve commit ancestry checks for candidate generations.

## GitHub Actions
- Grant minimum permissions.
- Pin third-party actions to immutable commit SHAs where practical.
- Never expose secrets to untrusted fork code.
- Keep write operations gated and auditable.
- Dependency/security failures are merge blockers unless explicitly reviewed with evidence.

## Tablet packaging
Only package files that are required at runtime. A file existing in the repository does not prove it is present or executed on the physical tablet.
