from pathlib import Path

watch = Path('grading_company_watch.py')
text = watch.read_text(encoding='utf-8')

old = '''                structured = (\n                    _service_changes(company, source_id, old.get("services", []) or [], services, checked_at)\n                    if old.get("verified_official_source") is True and old.get("parser_version") == PARSER_VERSION else []\n                )\n                changes.extend(structured)\n                old_fp = old.get("signal_fingerprint")\n                if old.get("parser_version") == PARSER_VERSION and old_fp and old_fp != fingerprint and not structured and not found:\n'''
new = '''                same_source_url = str(old.get("url") or "") == str(spec["url"])\n                structured = (\n                    _service_changes(company, source_id, old.get("services", []) or [], services, checked_at)\n                    if (\n                        same_source_url\n                        and old.get("verified_official_source") is True\n                        and old.get("parser_version") == PARSER_VERSION\n                    ) else []\n                )\n                changes.extend(structured)\n                old_fp = old.get("signal_fingerprint")\n                if (\n                    same_source_url\n                    and old.get("parser_version") == PARSER_VERSION\n                    and old_fp\n                    and old_fp != fingerprint\n                    and not structured\n                    and not found\n                ):\n'''
if text.count(old) != 1:
    raise SystemExit('structured-change anchor not found exactly once')
text = text.replace(old, new, 1)

old = '''                if old_verified and retained.get("services"):\n                    markets[spec["market"]] = {\n                        "currency": spec["currency"], "source": spec["url"],\n                        "services": retained["services"], "retained_last_good": True,\n                        "verified_official_source": True,\n                    }\n'''
new = '''                if old_verified and retained.get("services"):\n                    retained_source = str(retained.get("url") or spec["url"])\n                    markets[spec["market"]] = {\n                        "currency": spec["currency"], "source": retained_source,\n                        "services": retained["services"], "retained_last_good": True,\n                        "verified_official_source": True,\n                    }\n'''
if text.count(old) != 1:
    raise SystemExit('retained-market anchor not found exactly once')
text = text.replace(old, new, 1)

old = '''        prior_source = prev_sources.get(str(row.get("source_id", "")), {})\n        # A newly introduced official source is baseline inventory even when the\n        # repository already has snapshots for other companies/sources.\n        if not (isinstance(prior_source, dict) and prior_source.get("verified_official_source") is True):\n            continue\n'''
new = '''        source_id = str(row.get("source_id", ""))\n        prior_source = prev_sources.get(source_id, {})\n        current_source = sources.get(source_id, {})\n        # A newly introduced or migrated official source is baseline inventory even\n        # when the logical source_id already existed at a different URL.\n        if not (\n            isinstance(prior_source, dict)\n            and prior_source.get("verified_official_source") is True\n            and isinstance(current_source, dict)\n            and str(prior_source.get("url") or "") == str(current_source.get("url") or "")\n        ):\n            continue\n'''
if text.count(old) != 1:
    raise SystemExit('announcement baseline anchor not found exactly once')
text = text.replace(old, new, 1)
watch.write_text(text, encoding='utf-8')

test = Path('test_grading_company_watch_v215.py')
t = test.read_text(encoding='utf-8')
marker = '\n\nif __name__ == "__main__":\n    unittest.main()\n'
if t.count(marker) != 1:
    raise SystemExit('test footer anchor not found exactly once')
addition = r'''

    def test_source_url_migration_establishes_new_baseline_without_false_service_changes(self):
        old_url = "https://taggrading.com/pages/pricing"
        new_url = "https://taggrading.com/collections/grading-services-official"
        specs = ({"id": "tag-pricing", "kind": "pricing", "market": "US", "currency": "USD", "url": new_url},)
        previous = {
            "sources": {"tag-pricing": {
                "company": "TAG", "source_id": "tag-pricing", "kind": "pricing", "market": "US", "currency": "USD",
                "url": old_url, "status": "ok", "signal_fingerprint": "old-fingerprint",
                "services": [{"name": "Basic", "fee": 19.0, "currency": "USD", "availability": "open",
                              "source": old_url, "verified_official_source": True, "parser_version": watch.PARSER_VERSION}],
                "announcements": [], "verified_official_source": True, "parser_version": watch.PARSER_VERSION,
            }},
            "announcements": [], "history": [],
        }
        html = ("<html><body>TAG GRADING SERVICES OFFICIAL "
                "Quick buy GRADING | BASIC From $22.00 USD Sold Out "
                "Quick buy GRADING | STANDARD From $39.00 USD Sold Out</body></html>")
        with mock.patch.object(watch, "WATCH_SOURCES", {"TAG": specs}):
            data = watch.collect(previous, fetcher=lambda _url: html)
        self.assertEqual(data["recent_changes"], [])
        self.assertEqual(data["sources"]["tag-pricing"]["url"], new_url)
        self.assertEqual(data["companies"]["TAG"]["markets"]["US"]["source"], new_url)

    def test_failed_source_url_migration_retains_last_good_original_source_identity(self):
        old_url = "https://taggrading.com/pages/pricing"
        new_url = "https://taggrading.com/collections/grading-services-official"
        specs = ({"id": "tag-pricing", "kind": "pricing", "market": "US", "currency": "USD", "url": new_url},)
        previous = {
            "sources": {"tag-pricing": {
                "company": "TAG", "source_id": "tag-pricing", "kind": "pricing", "market": "US", "currency": "USD",
                "url": old_url, "status": "ok", "signal_fingerprint": "last-good",
                "services": [{"name": "Basic", "fee": 19.0, "currency": "USD", "availability": "open",
                              "source": old_url, "verified_official_source": True, "parser_version": watch.PARSER_VERSION}],
                "announcements": [], "verified_official_source": True, "parser_version": watch.PARSER_VERSION,
            }},
            "announcements": [], "history": [],
        }
        with mock.patch.object(watch, "WATCH_SOURCES", {"TAG": specs}):
            data = watch.collect(previous, fetcher=mock.Mock(side_effect=OSError("new source temporarily unavailable")))
        source = data["sources"]["tag-pricing"]
        market = data["companies"]["TAG"]["markets"]["US"]
        health = data["companies"]["TAG"]["source_health"][0]
        self.assertEqual(source["status"], "degraded")
        self.assertEqual(source["url"], old_url)
        self.assertEqual(market["source"], old_url)
        self.assertTrue(market["retained_last_good"])
        self.assertEqual(health["url"], new_url)

    def test_migrated_news_source_does_not_emit_all_current_links_as_new_announcements(self):
        old_url = "https://taggrading.com/pages/news"
        new_url = "https://taggrading.com/"
        specs = ({"id": "tag-home", "kind": "news", "market": "GLOBAL", "currency": "USD", "url": new_url},)
        previous = {
            "sources": {"tag-home": {
                "company": "TAG", "source_id": "tag-home", "kind": "news", "market": "GLOBAL", "currency": "USD",
                "url": old_url, "status": "ok", "signal_fingerprint": "old-fingerprint", "services": [], "announcements": [],
                "verified_official_source": True, "parser_version": watch.PARSER_VERSION,
            }},
            "announcements": [], "history": [],
        }
        html = ("<html><body>TAG grading service pricing event announcement and updates. "
                "<a href='/blogs/news/grading-service-update'>Grading service pricing update 2026/09/13</a>"
                "</body></html>")
        with mock.patch.object(watch, "WATCH_SOURCES", {"TAG": specs}):
            data = watch.collect(previous, fetcher=lambda _url: html)
        self.assertEqual(data["recent_changes"], [])
        self.assertEqual(len(data["announcements"]), 1)
'''
t = t.replace(marker, addition + marker, 1)
test.write_text(t, encoding='utf-8')
