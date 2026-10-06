# TCG Grader agent-skill source review

This repository uses a **project-authored skill pack**. External GitHub projects were reviewed for engineering patterns, but third-party skill text/code was not vendored into the five TCG skills.

## Reviewed sources

| Source | What was useful | Reuse decision |
|---|---|---|
| `shiong-tan/repo-scaffold-skill` | repository quality gates, security-first scaffolding, CI/testing structure | CC0 source; concepts adapted into TCG-specific rules |
| `trailofbits/skills` | differential review, static analysis, property-based testing, supply-chain review patterns | repository license is CC BY-SA 4.0; no skill text/code copied into the TCG pack |
| `stas00/python-cookbook` | standard-library-first Python, testing/debugging/runtime hygiene | source identifies CC BY-SA 4.0; no cookbook text copied |
| `marcuspmd/smart-code-review` | multi-lens review and targeted tool execution | no root LICENSE was found during review; ideas only, no text/code vendored |
| `SpillwaveSolutions/mastering-github-agent-skill` | CI monitoring and GitHub workflow discipline | no root LICENSE was found during review; ideas only, no text/code vendored |

## Repository-owned skills

- `tcg-code-review`
- `tcg-python-quality`
- `tcg-security-review`
- `tcg-property-testing`
- `tcg-github-ci`

The canonical project copy is mirrored byte-for-byte under both:

- `.agents/skills/<name>/SKILL.md`
- `.codex/skills/<name>/SKILL.md`

`agent_skills_guard.py` validates the mirrors and frontmatter without executing skill text. Graphify intentionally excludes `.agents/` and `.codex/` from the application architecture graph so control-plane instructions do not recursively become product architecture.

## Safety boundary

These skills are development guidance only. They do not grant runtime autonomy, source-code self-rewrite, arbitrary-command generation, direct-main writes, verification bypass, market-direction invention, or card price/grade/stock/release/event fact invention. Existing TCG Grader runtime gates remain authoritative.
