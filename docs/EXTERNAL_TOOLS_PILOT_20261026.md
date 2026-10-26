# External tools pilot — OpenHands / Crawl4AI (2026-10-26)

## Scope and evidence
- Target: TCG Grader; base main c5bf5608b87b19d72e5b9f73a3aa0a466230f397.
- This is a **draft, offline and read-only experiment**, not production integration.
- The evaluator in execution/external_tool_pilot_v1.py has no network, shell, LLM, repository, tablet, model, database or cloud dependency.
- It cannot publish a card, price, image, event, grading result, or update; every accepted item is marked REVIEW_ONLY and publishable=False.
- Python synthetic unit tests: 20 cases passing in a separate Python environment after bounded-input hardening. This is NOT proof of GitHub CI or Lenovo physical runtime.
- Crawl4AI itself was **not** installed or executed; the test environment could not resolve the package index. Actual live extraction, throughput, source coverage, CPU/RAM and cache behavior are NOT measured.
- OpenHands itself was **not** installed or executed; no model, API key, sandbox or runtime was provisioned.

## Decision and separation
1. Crawl4AI is a **candidate** for separate, user-approved official-web evidence discovery. It must not replace existing verified TCG collectors or bypass evidence lineage and freshness checks. A future actual adapter must use trusted exact host allowlists, bounded concurrency/timeouts, check robots/terms, enforce *all-hop* egress + DNS pinning, and require a known final URL before parsing. Pre/post URL comparison here cannot prove redirect/SSRF protection.
2. OpenHands is a **candidate** for isolated code-review and test-generation tasks, never an unrestricted tablet or auto-merge agent. Use a restricted container, read-only project copy, no mounted secrets, no main push, no elevated filesystem access, no paid model/API usage without approval. Keep human review plus current-head CI as authoritative. An agent suggestion is not an approval.
3. Both tools remain optional. Existing Graphify, TCG skills, source verification and last-good protections keep their priority.

## Offline acceptance tests (synthetic; not live site evidence)
- Allowed HTTPS origin + recent timezone-aware observation => only REVIEW_ONLY, never publishable.
- Non-HTTPS, credentials, ports, malformed hosts, IP literals, localhost, internal host and mismatched final host => BLOCKED.
- Stale/future/naive observation timestamps, excessive content and missing data => BLOCKED.
- Prompt-injection text remains inert and does not appear in the receipt.
- Duplicate comparison only reports prospective review candidates and never asserts an actual production improvement.
- Comparison is limited to 5,000 receipts per input list and validates types, evidence metadata and SHA-256 shape. Malformed accepted receipts reject the batch rather than crashing.
- Timestamp lengths, hostname formats, Unicode byte sizes and invalid UTF-8 surrogate text fail closed. No raw page text is returned.

Run on a separate source copy (no network requirements):

    python -m unittest discover -s execution/tests -p 'test_external_tool_pilot_v1.py' -v
    python execution/external_tool_pilot_v1.py

## Required criteria before any production proposal
- Dependency review: version/license, SBOM/CVEs, no unapproved data exfiltration or paid endpoint.
- Privacy/security: reject private/rebound/redirected endpoints at the network layer; robots and terms verified; rate limits, retries and no bot-protection circumvention.
- Reliability: 403/429/non-2xx, changing DOM, JS-heavy websites, unavailable service, truncated and stale text, HTML attacks, duplicate/mirror lineage.
- Quality: official-source citations, region/language/printing identity, independent corroboration, image rights, date and source trust.
- Performance: measured locally against the **same permitted sources and windows**, CPU, RAM, p95 latency, success rate, duplicate rates and failure recovery. No invented baseline.
- Offline-only synthetic 5,000+5,000 receipt comparison: approximately 37 ms on a separate test runtime, one measurement, not a p95, not a Lenovo/Termux measurement, and not live crawling throughput.
- Deployment: no tablet runtime changes or dependencies; separate reviewed PR and current-head mandatory CI; real Lenovo receipt required to claim device validation.

## Public documentation checked
- https://github.com/unclecode/crawl4ai — latest published project README reports 0.9.5 dated 2026-10-14
- https://github.com/unclecode/crawl4ai/security — fixes for SSRF and code-injection paths through 0.9.5
- https://docs.crawl4ai.com/core/quickstart/ — AsyncWebCrawler needs a browser runtime
- https://docs.crawl4ai.com/api/parameters/ — `CrawlerRunConfig(check_robots_txt=True)` (default false) and bounded settings
- https://docs.python.org/3/library/urllib.parse.html#url-parsing-security — URL split functions are not URL security validation
- https://github.com/OpenHands/docs/blob/main/openhands/usage/advanced/custom-sandbox-guide.mdx — agent-server container isolation
- https://github.com/OpenHands/OpenHands — latest published tag v1.33.0 at the review date
- https://github.com/OpenHands/OpenHands/blob/main/README.md — sandboxless runs may access host filesystem

## Hold criteria
No automatic merge, deploy, package installation or tablet update. Do not run a live crawler or agent merely because this PR exists. The evaluator only consumes synthetic or separately reviewed extraction outputs. If any current-head CI or integrity gate fails, keep the PR unmerged and preserve main / last-good.
