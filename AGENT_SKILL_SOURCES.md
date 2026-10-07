# TCG Grader agent-skill source review

This repository uses a **project-authored skill pack**. External GitHub projects were reviewed for engineering patterns, but third-party skill text/code was not vendored into the TCG skills.

## Reviewed sources

| Source | What was useful | Reuse decision |
|---|---|---|
| `shiong-tan/repo-scaffold-skill` | repository quality gates, security-first scaffolding, CI/testing structure | CC0 source; concepts adapted into TCG-specific rules |
| `trailofbits/skills` | differential review, static analysis, property-based testing, supply-chain review patterns | repository license is CC BY-SA 4.0; no skill text/code copied into the TCG pack |
| `stas00/python-cookbook` | standard-library-first Python, testing/debugging/runtime hygiene | source identifies CC BY-SA 4.0; no cookbook text copied |
| `marcuspmd/smart-code-review` | multi-lens review and targeted tool execution | no root LICENSE was found during review; ideas only, no text/code vendored |
| `SpillwaveSolutions/mastering-github-agent-skill` | CI monitoring and GitHub workflow discipline | no root LICENSE was found during review; ideas only, no text/code vendored |
| `addyosmani/agent-skills` | TDD, root-cause debugging, security, performance, CI, observability, source-driven workflow patterns | concepts reviewed and rewritten for TCG Grader; no third-party skill text/code vendored |
| `anthropics/skills` | skill packaging, frontmatter, progressive-disclosure and evaluation structure | structure reviewed and adapted; no third-party skill text/code vendored |
| `NousResearch/hermes-agent` | Android-aware update verification, deployment-kind checks, low-storage correctness patterns | concepts reviewed only; no source code or skill text copied |
| `sipeed/picoclaw` and `liaru-lab/henyo` | Android/Termux setup, verification harness, safe device deployment patterns | concepts adapted into TCG-specific deployment guidance; no third-party code vendored |
| `bda-research/node-crawler` and `diegosouzapw/awesome-omni-skills` | bounded crawler queues, rate limiting, differential scraping, provenance/dedup patterns | ideas rewritten for TCG collectors; no third-party skill text copied |
| `Xerialen/komodobots` | ML review emphasis on leakage, drift, evidence quality, and false confidence | review concepts only; no repository text copied |
| `microsoft/Foundry-AI-solution-templates-creation` | explicit schema/input-output contracts, confidence/error fields, pipeline validation | contract concepts adapted; no template code copied |
| `github/awesome-copilot` (`webapp-testing`, `ui-screenshots`, `web-design-reviewer`, `test-gap-audit`, `poka-yoke`, `pr-screenshots`) | local browser QA, visual evidence, UI finish gates, behavior-focused coverage audits, structural mistake-proofing | concepts reviewed and rewritten for TCG Grader; no third-party skill text/code vendored |
| `cloudflare/skills` (`web-perf`) | browser performance tracing, network/resource diagnosis, evidence-first optimization | concepts adapted to local tablet/runtime measurement only; no Cloudflare service dependency and no skill text/code copied |
| `jwynia/agent-skills` (`pwa-development`) | service-worker cache strategy, stale-update diagnosis, install/offline checks | PWA concepts adapted to the existing local service worker and compatibility ABI; no skill text/code copied |
| `thedaviddias/Front-End-Checklist` (`frontend-checklist-global`) | accessibility, focus, layout stability, responsive/mobile frontend audit coverage | checklist concepts adapted to the TCG UI finish gate; no external MCP/runtime dependency required |

## Repository-owned skills

Repository-owned skills use the `tcg-*` namespace. The required core is:

- `tcg-code-review`
- `tcg-python-quality`
- `tcg-security-review`
- `tcg-property-testing`
- `tcg-github-ci`

Additional TCG-specific skills may be added for focused domains such as regression testing, debugging/recovery, performance budgets, observability, source/evidence validation, and vision/grading. They do not need a hard-coded registry entry: `agent_skills_guard.py` dynamically discovers every `tcg-*` skill.

Every discovered project skill must be mirrored byte-for-byte under both:

- `.agents/skills/<name>/SKILL.md`
- `.codex/skills/<name>/SKILL.md`

The six local-only quality skills are additionally mirrored byte-for-byte under `.github/skills/<name>/SKILL.md` so GitHub-side agent tooling sees the same instructions. The guard validates the agent/Codex trees, the required GitHub mirrors for that local-only set, frontmatter, mirror identity, bounded file size, required core presence, local-only boundary text, and Graphify control-plane exclusion without executing skill text.

## Graphify boundary

Graphify intentionally excludes `.agents/` and `.codex/` from the application architecture graph so agent control-plane instructions do not recursively become product architecture.

## Local-only execution boundary

The current TCG Grader skill pack does not use Colab, cloud compute/training, hosted browser/device farms, cloud rendering, or a cloud control plane. Browser/UI/PWA verification is designed to run against the local repository, the tablet local server, deterministic Node/Python harnesses, and an optional user-owned local browser. GitHub remains source/PR/CI infrastructure, not a live runtime or learning node.

## Safety boundary

These skills are development guidance only. They do not grant runtime autonomy, source-code self-rewrite, arbitrary-command generation, direct-main writes, verification bypass, market-direction invention, or card price/grade/stock/release/event fact invention. Existing TCG Grader runtime gates remain authoritative.
