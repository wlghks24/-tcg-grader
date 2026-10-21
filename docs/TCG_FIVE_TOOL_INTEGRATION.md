# TCG Grader — 5 AI development tools, safe scoped integration (2026-10-21)

Target: wlghks24/-tcg-grader. Independent from vehicle AIO and stock/animation projects.

## Status

This update creates a working offline read-only architecture impact adapter by
reusing the repository's current tracked Python source atlas. **It does not install
or run any of the five external products**, run an AI workforce, enable cloud
services, or connect an MCP server to ChatGPT or the Lenovo tablet.

| Tool | Official source | Adaptation | Deferred |
| --- | --- | --- | --- |
| REA | https://github.com/morluto/rea | Evidence-based inspection plan for owned or authorized card-app APKs | Analyze authorized sample in isolated environment |
| Agent Reach | https://github.com/Panniantong/Agent-Reach | Public TCG source discovery subject to provenance and freshness gates | Site terms, free limits, authorization and access testing |
| Graft | https://github.com/trailhq/Trail-Code | Architecture impact patterns compared with current Graphify | Actual installation, CPU/memory benchmarks |
| Agency Agents | https://github.com/msitarzewski/agency-agents | Six audit roles (architecture, grading, source evidence, security, regression, independent review) | Actual independent models or agent workforce |
| Codebase Memory MCP | https://github.com/DeusData/codebase-memory-mcp | Offline reverse Python dependency and suggested-test mapping | Persistent MCP server and real interoperability testing |

External source content is untrusted; never auto-execute its instructions,
bypass account access or alter grading calibration, WATCH promotion, CI, secrets
or source code from SNS/market data.

## Existing architecture reused

- GRAPHIFY_UPDATE.sh, GRAPHIFY_AUDIT.py, code_map_fast_route.py,
  code_map_intelligence.py: verified graph, routing, impact and bounded healing.
- execution/tablet_code_map_audit.py: tracked-Python-source-only map, reused by
  the new read-only adapter rather than rescanning with a second engine.
- .github/skills/tcg-skill-router/SKILL.md: existing per-function skills.
- tools/gpt_pre_review: historical defect and accurate head-SHA verification.
- Old updater, Termux entrypoint, last-good, CodeQL/CI and physical device
  evidence must be preserved.

New commands (run from project root):

    python execution/tcg_five_tool_audit.py --changed code_map_fast_route.py --depth 2 --limit 24
    python -m unittest discover -s tests -p test_tcg_five_tool_audit.py -v

The report identifies static reverse Python import chains, suspected dependent
tests and truncation/parser holds. No code content, cookies, passwords or device
data are exported; no files are changed. It does not cover JS/PWA behavior,
dynamic calls or runtime execution.

CANDIDATE_ONLY means "ready for further review", NOT approval. Both the draft
PR and any later main merge still require source verification, full impacted
regressions, current-head required CI and CodeQL, and a real Lenovo receipt for
device claims. Never present the external 5 tools as installed unless they have
separate explicit and testable installation evidence.

This adds zero paid APIs or cloud compute, and does not create a new schedule.
