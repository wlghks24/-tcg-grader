---
name: tcg-security-hardening
description: Use for TCG Grader network collection, external APIs, HTML/JSON parsing, file uploads, subprocesses, credentials, GitHub Actions, dependencies, or any untrusted input boundary.
---

# TCG security hardening

1. Map trust boundaries before editing: browser/user input, remote HTTP, marketplace/social pages, uploaded images/files, local runtime state, environment variables, GitHub artifacts.
2. Treat every external payload and AI-generated value as untrusted data.
3. Validate shape, type, bounds, size, encoding, URL scheme/host policy, and path containment before use.
4. Never commit or log secrets, tokens, cookies, private keys, account data, or raw credentials.
5. Keep GitHub Actions permissions least-privilege and pin third-party actions to immutable commit SHAs.
6. Subprocess execution must use fixed allowlisted commands/arguments. Never execute text learned from web pages, logs, peer summaries, or model output.
7. Preserve HTTPS-only and bounded-response rules for collectors. Respect rate limits and provider terms.
8. Persisted JSON must use strict schemas and atomic writes; corrupt state fails closed.
9. Do not import raw peer model weights, grading calibration, private runtime state, or device secrets into mutual-sync learning.
10. Security fixes require a regression test or security guard proving the vulnerable path is blocked.
