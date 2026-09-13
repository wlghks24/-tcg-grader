from pathlib import Path

watch = Path('grading_company_watch.py')
text = watch.read_text(encoding='utf-8')

old = 'PARSER_VERSION = 2\n\nALLOWED_HOSTS = {'
new = '''PARSER_VERSION = 2\n# Provider-specific revisions prevent a parser implementation change from being\n# misreported as a real grading-company price/service change. Unchanged providers\n# stay on the global parser version so they do not lose a detection cycle.\nSERVICE_PARSER_VERSIONS = {\n    (\"PSA\", \"US\"): 3,\n    (\"PSA\", \"JP\"): 3,\n    (\"BGS\", \"US\"): 3,\n}\n\n\ndef _service_parser_version(company: str, market: str) -> int:\n    return SERVICE_PARSER_VERSIONS.get((company, market), PARSER_VERSION)\n\n\nALLOWED_HOSTS = {'''
if text.count(old) != 1:
    raise SystemExit('parser-version constant anchor mismatch')
text = text.replace(old, new, 1)

old = '''def _service_row(name: str, observed_label: str, currency: str, source: str, *,\n                 fee=None, turnaround=None, max_value=None, availability: str = \"unknown\") -> dict:\n    row = {\n        \"name\": name, \"observed_label\": observed_label, \"currency\": currency,\n        \"availability\": availability, \"source\": source, \"verified_official_source\": True,\n        \"parser_version\": PARSER_VERSION,\n    }\n'''
new = '''def _service_row(name: str, observed_label: str, currency: str, source: str, *,\n                 fee=None, turnaround=None, max_value=None, availability: str = \"unknown\",\n                 parser_version: int = PARSER_VERSION) -> dict:\n    row = {\n        \"name\": name, \"observed_label\": observed_label, \"currency\": currency,\n        \"availability\": availability, \"source\": source, \"verified_official_source\": True,\n        \"parser_version\": parser_version,\n    }\n'''
if text.count(old) != 1:
    raise SystemExit('service-row anchor mismatch')
text = text.replace(old, new, 1)

old = '''def _parse_bgs_services(currency: str, text: str, source: str) -> list[dict]:\n    \"\"\"Parse Beckett's current tier cards, including both Base price variants.\"\"\"\n    tier_names = (\"Base\", \"Standard\", \"Express\", \"Priority\")\n'''
new = '''def _parse_bgs_services(currency: str, text: str, source: str) -> list[dict]:\n    \"\"\"Parse Beckett's current tier cards, including both Base price variants.\"\"\"\n    parser_version = _service_parser_version(\"BGS\", \"US\")\n    tier_names = (\"Base\", \"Standard\", \"Express\", \"Priority\")\n'''
if text.count(old) != 1:
    raise SystemExit('BGS parser anchor mismatch')
text = text.replace(old, new, 1)

text = text.replace(
    'fee=base_prices[0], turnaround=base_days, availability=_availability(without_window),\n    ))',
    'fee=base_prices[0], turnaround=base_days, availability=_availability(without_window),\n        parser_version=parser_version,\n    ))',
    1,
)
text = text.replace(
    'fee=base_prices[1], turnaround=base_days, availability=_availability(with_window),\n    ))',
    'fee=base_prices[1], turnaround=base_days, availability=_availability(with_window),\n        parser_version=parser_version,\n    ))',
    1,
)
text = text.replace(
    'availability=_availability(segment),\n        ))',
    'availability=_availability(segment), parser_version=parser_version,\n        ))',
    1,
)

old = '''def _parse_alias_services(company: str, market: str, currency: str, text: str, source: str) -> list[dict]:\n    rows: list[dict] = []\n    alias_map = SERVICE_ALIASES.get((company, market), {})\n'''
new = '''def _parse_alias_services(company: str, market: str, currency: str, text: str, source: str) -> list[dict]:\n    rows: list[dict] = []\n    parser_version = _service_parser_version(company, market)\n    alias_map = SERVICE_ALIASES.get((company, market), {})\n'''
if text.count(old) != 1:
    raise SystemExit('alias parser anchor mismatch')
text = text.replace(old, new, 1)

old = '''        rows.append(_service_row(\n            canonical, alias, currency, source, fee=fee, turnaround=turnaround,\n            max_value=max_value, availability=availability,\n        ))\n'''
new = '''        rows.append(_service_row(\n            canonical, alias, currency, source, fee=fee, turnaround=turnaround,\n            max_value=max_value, availability=availability, parser_version=parser_version,\n        ))\n'''
if text.count(old) != 1:
    raise SystemExit('alias service-row call anchor mismatch')
text = text.replace(old, new, 1)

old = '''def _service_changes(company: str, source_id: str, before: list[dict], after: list[dict], checked_at: str) -> list[dict]:\n'''
new = '''def _service_changes(company: str, source_id: str, before: list[dict], after: list[dict], checked_at: str,\n                     parser_version: int = PARSER_VERSION) -> list[dict]:\n'''
if text.count(old) != 1:
    raise SystemExit('service-changes signature anchor mismatch')
text = text.replace(old, new, 1)
text = text.replace('"verified_official_source": True, "parser_version": PARSER_VERSION,', '"verified_official_source": True, "parser_version": parser_version,', 3)

old = '''        for spec in specs:\n            source_id = spec[\"id\"]\n            old = prev_sources.get(source_id, {}) if isinstance(prev_sources.get(source_id), dict) else {}\n            try:\n'''
new = '''        for spec in specs:\n            source_id = spec[\"id\"]\n            source_parser_version = (\n                _service_parser_version(company, spec[\"market\"])\n                if \"pricing\" in spec[\"kind\"] else PARSER_VERSION\n            )\n            old = prev_sources.get(source_id, {}) if isinstance(prev_sources.get(source_id), dict) else {}\n            try:\n'''
if text.count(old) != 1:
    raise SystemExit('collect source-parser-version anchor mismatch')
text = text.replace(old, new, 1)

old = '''                    \"services\": services, \"announcements\": found, \"verified_official_source\": True,\n                    \"parser_version\": PARSER_VERSION,\n'''
new = '''                    \"services\": services, \"announcements\": found, \"verified_official_source\": True,\n                    \"parser_version\": source_parser_version,\n'''
if text.count(old) != 1:
    raise SystemExit('source row parser-version anchor mismatch')
text = text.replace(old, new, 1)

old = '''                    _service_changes(company, source_id, old.get(\"services\", []) or [], services, checked_at)\n                    if (\n                        same_source_url\n                        and old.get(\"verified_official_source\") is True\n                        and old.get(\"parser_version\") == PARSER_VERSION\n                    ) else []\n'''
new = '''                    _service_changes(\n                        company, source_id, old.get(\"services\", []) or [], services, checked_at,\n                        parser_version=source_parser_version,\n                    )\n                    if (\n                        same_source_url\n                        and old.get(\"verified_official_source\") is True\n                        and old.get(\"parser_version\") == source_parser_version\n                    ) else []\n'''
if text.count(old) != 1:
    raise SystemExit('structured comparison anchor mismatch')
text = text.replace(old, new, 1)
text = text.replace('and old.get("parser_version") == PARSER_VERSION\n                    and old_fp', 'and old.get("parser_version") == source_parser_version\n                    and old_fp', 1)

watch.write_text(text, encoding='utf-8')

test = Path('test_grading_company_watch_v215.py')
t = test.read_text(encoding='utf-8')
footer = '\n\nif __name__ == "__main__":\n    unittest.main()\n'
if t.count(footer) != 1:
    raise SystemExit('test footer anchor mismatch')
addition = r'''

    def test_provider_parser_revisions_are_isolated_to_changed_pricing_parsers(self):
        self.assertEqual(watch._service_parser_version("PSA", "US"), 3)
        self.assertEqual(watch._service_parser_version("PSA", "JP"), 3)
        self.assertEqual(watch._service_parser_version("BGS", "US"), 3)
        self.assertEqual(watch._service_parser_version("CGC", "US"), watch.PARSER_VERSION)
        self.assertEqual(watch._service_parser_version("TAG", "US"), watch.PARSER_VERSION)

    def test_provider_parser_revision_upgrade_establishes_new_baseline(self):
        spec = {"id": "psa-us-pricing", "kind": "pricing", "market": "US", "currency": "USD",
                "url": "https://www.psacard.com/services/tradingcardgrading"}
        previous = {"sources": {"psa-us-pricing": {
            "company": "PSA", "source_id": "psa-us-pricing", "kind": "pricing", "market": "US",
            "currency": "USD", "url": spec["url"], "status": "ok", "checked_at": "2026-09-12T00:00:00+00:00",
            "signal_fingerprint": "old-parser-fingerprint", "verified_official_source": True,
            "parser_version": watch.PARSER_VERSION,
            "services": [{"name": "Express", "fee": 99.0, "availability": "open"}],
            "announcements": [],
        }}, "announcements": [], "history": []}
        body = (
            "Official PSA grading service pricing and turnaround information. "
            "Regular $79.99/Card Max Insured Value: $1,500 Estimated Turnaround Time: 70 Business Days Get Started "
            "Express $149.00/Card Max Insured Value: $2,500 Estimated Turnaround Time: 25 Business Days Get Started "
            "Super Express $299.00/Card Max Insured Value: $5,000 Estimated Turnaround Time: 10 Business Days Get Started"
        )
        with mock.patch.object(watch, "WATCH_SOURCES", {"PSA": (spec,)}):
            data = watch.collect(previous, fetcher=lambda _url: body)
        source = data["sources"]["psa-us-pricing"]
        self.assertEqual(source["parser_version"], 3)
        self.assertTrue(source["services"])
        self.assertFalse(any(
            row.get("source_id") == "psa-us-pricing" and row.get("type") in {
                "service_added", "service_removed", "service_changed", "official_page_changed_unparsed"
            }
            for row in data["recent_changes"]
        ))
'''
t = t.replace(footer, addition + footer, 1)
test.write_text(t, encoding='utf-8')
