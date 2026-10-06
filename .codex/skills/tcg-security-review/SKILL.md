---
name: tcg-security-review
description: Perform security-focused review and hardening for TCG Grader Python, shell, browser/PWA, GitHub Actions, updater, collection, and autonomous-learning code.
version: "1.0.0"
---

# TCG Grader Security Review

## Always inspect
- Secrets/tokens/credentials in source, logs, artifacts, URLs, or exception text.
- Shell injection and unsafe interpolation in Bash, Python subprocess, Task Scheduler, and Termux launchers.
- Path traversal, symlink attacks, unsafe temp files, and destructive update/recovery behavior.
- SSRF/open redirects/untrusted URLs, insecure HTTP, authentication/verification bypass, and excessive GitHub permissions.
- Browser injection/XSS in generated HTML, labels, market/event text, or OCR-derived values.
- Unsafe model/autonomy behavior: arbitrary command execution, source-code generation/rewrite, direct main writes, fact invention, verification bypass, untrusted peer-state promotion.

## Static-analysis order
1. Read the exact diff and routed impact surface.
2. Compile/lint with repository-native checks.
3. Search dangerous sinks and trust-boundary crossings.
4. If already available in the environment, use Semgrep/CodeQL-style analysis as an additional signal.
5. Never auto-install or execute an unreviewed third-party scanner inside production runtime.

## Security invariants
- Least privilege GitHub Actions permissions.
- Pinned or repository-approved action revisions.
- Verified evidence cannot be downgraded by community/search repetition.
- Unverified evidence cannot be upgraded to official/verified by popularity or model confidence.
- Failure keeps the last verified policy/model/data where the existing contract requires it.
- Recovery never bypasses integrity or verification gates.
