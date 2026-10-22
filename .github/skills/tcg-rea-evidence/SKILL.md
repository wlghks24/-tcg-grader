---
name: tcg-rea-evidence
description: 'Optional REA investigation of an authorized shipped app, APK, Electron bundle, or binary when source and normal repository tools cannot establish the behavior. Never use for ordinary TCG repository QA.'
---

# Optional REA evidence workflow (manual / local only)

## When to route here
Use REA only when an authorized, concrete executable/package (APK, ASAR, JS/Electron application tree, native binary) is supplied and a claim depends on its shipped code or observed behavior. Use ordinary source review, Python tests, regression recovery, supply-chain checks, and the existing tablet QA skills for this repository. Do **not** auto-install or auto-run REA just because its documentation exists.

## Mandatory boundaries
- Analyze only software the owner controls or is legally authorized to inspect. Never bypass login, DRM, subscriptions, rate limits, anti-bot restrictions or technical protections.
- Reverse engineering is evidence collection, not a license to copy proprietary source/assets. Prefer independent implementations, with permission and compatible licenses.
- This repository's runtime, learning, browser QA and skill execution are **local-only**. Do not introduce hosted REA jobs, GitHub Actions analysis, cloud file uploads, network capture, or paid API/services. No automatic changes to GitHub or the Lenovo tablet.
- REA is **not installed or registered** merely by adding this skill. MCP registration belongs to the chosen local coding agent, not GitHub. Do not claim a verified device run without a device transcript.
- Do not run arbitrary downloaded install scripts or enable Hopper, proprietary analysis engines, ADB debugging, network interception, or executable launch without target-specific consent and a reviewed impact plan. Use a free provider only when its license, support and prerequisites are verified.
- Exclude secrets, tokens, private customer data, and copyrighted third-party binaries from reports and commits. Make ephemeral local copies for analysis; keep raw artifacts outside the repository.

## Local setup protocol (operator-run, never automatic)
Source of truth: https://github.com/morluto/rea ; setup: https://github.com/morluto/rea/blob/main/docs/installation.md ; security: https://github.com/morluto/rea/blob/main/DISCLAIMER.md

1. Verify the **actual** host OS/architecture and supported Node.js and npm; REA currently requires Node 22.19+ in the 22.x series, Node 24.11+ in the 24.x series, or Node 26+. On Android/Termux, verify relevant capability separately: REA has experimental Termux browser smoke-test source, **not** a blanket guarantee of APK/native provider support on an ARM tablet.
2. Inspect the official REA release and npm package before downloading. A `npx` doctor call can download/cache a package; it is not wholly offline.
3. Where a compatible host and an installed coding client are available, preview **read-only configuration changes** (replace `gemini_cli` with an actually present client):
   ```bash
   npx -y rea-agents@latest doctor --json
   npx -y rea-agents@latest setup --client gemini_cli --dry-run --json
   ```
4. Read the predicted write paths, backups and dependencies. Only after explicit review and local consent, run `npx rea-agents@latest setup --client gemini_cli`. Do not accept optional proprietary engines. Restart the coding client and verify that the MCP tools really appear. Prefer pinning a verified npm version over `@latest` once validated.
5. If client integration is unavailable, use supported one-shot CLI operations for an operator-supplied target on a verified host. E.g. `npx -y rea-agents@latest analyze-javascript-application /absolute/path/to/extracted-app --json`; static JS analysis needs no Hopper/Ghidra. Android APK class/method inspection separately needs a JDK and headless JADX, and supported host checks; see the official Android analysis guide.
6. If diagnostics fail, record the exact blocker (unsupported host, missing Node/client/provider, malformed config, target absent) as HOLD. Never silently switch to hosted analysis or claim REA is active.

## Required analysis report
Record authorized target and objective; file digest and provenance; CLI/MCP/provider versions; host/environment; exact bounded commands; evidence with source positions/identifiers; observed versus inferred behavior; unknowns/limitations; independent implementation proposal; licensing and privacy review; focused/regression/security tests; rollback; and an explicit PASS/HOLD/FAIL decision.

No source modification or device deployment follows automatically from REA findings. Re-run the existing project router and first-pass GPT review before any reviewed PR or later local deployment.
