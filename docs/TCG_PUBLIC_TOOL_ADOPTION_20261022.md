# TCG Grader — Fincept / Vibe-Trading / Camofox adaptation (2026-10-22)

**Project:** `wlghks24/-tcg-grader`, independent of private vehicle AIO and Stock AI.
**Status:** Reviewed patterns and deterministic *offline triage* added; three products are **not installed, connected or running**.

| Reference | Exact upstream | TCG-safe adapted idea | Status |
|---|---|---|---|
| Fincept Terminal | https://github.com/Fincept-Corporation/FinceptTerminal | Source-labeled dashboard, coverage/freshness, comparable evidence for graded cards and sealed BOX listings | Concept only |
| Vibe-Trading | https://github.com/HKUDS/Vibe-Trading | Independent scenario review and historical replay of card-valuation assumptions (NOT brokerage or stocks) | Concept only |
| camofox-browser | https://github.com/jo-inc/camofox-browser | Local owned-app UI snapshots/accessibility investigation using already-approved local browser QA | Concept only |

- Fincept open-source code is AGPL-3.0-or-later; source or UI code must not be copied into TCG without independent license/commercial-use review. Brand and logos are not reused. AI model and market-data costs are not automatically free.
- Vibe-Trading and Camofox projects advertise MIT licensing, but their dependencies, external services, accounts, and live execution remain separately reviewable.
- TCG grading/market pricing remains card/series/set/language/edition/condition/printing-specific; do not mistake stock-market algorithms for verified card market pricing. No automatic buy/sell or speculative expected-price claims.
- Web/source collection respects robots, service terms, rate limits, published API terms, and login boundaries. Never use Camofox stealth/spoofing to bypass access controls or bot-detection; no scraping of private sessions or cookie transfer.
- Source freshness, actual listing provenance and independent lineage are required before a market fact can be promoted. No fabricated realtime data, proprietary API entitlement, or 100+ source coverage claims.
- Existing Graphify, code map, `AGENTS.md`/skill routing, free/local Termux runtime, tablet last-good, TCG WATCH promotion, OCR/grading calibration and regression rules remain authoritative.

## Implemented now

`execution/external_tools_adoption_gate.py` is a standard-library *advisory* risk gate for the three upstream references. It rejects risky capabilities, unverified repo identity and paid features, labels permissible project-domain patterns as `CONCEPT_ONLY`, and always reports no real installation or runtime validation. It **does not** enforce browser network traffic or control runtime agents.

Sample:
`python execution/external_tools_adoption_gate.py --tool fincept --capability evidence_dashboard_pattern --source https://github.com/Fincept-Corporation/FinceptTerminal`

Run regression:
`python -m unittest discover -s tests -p test_external_tools_adoption_gate.py -v`

## Before enabling a real integration

1. Independent official upstream SHA/license/security review; identify exact needed module, do not vendor entire codebase.
2. Offline fixture tests, source lineage/freshness, failure/403/429, malformed data, memory and CPU budgets.
3. Compare any new collector/UI against existing local-only methods to prove added value; avoid duplicate processes.
4. New PR + current-head required CI/CodeQL/integrity + GPT first review; no merges into main without approval.
5. Lenovo real device evidence required before any claim about tablet execution or image collection.

Financial auto-trading belongs only to a separately approved Stock AI project, not here.
