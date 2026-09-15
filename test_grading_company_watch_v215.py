#!/usr/bin/env python3
from __future__ import annotations

import unittest
from unittest import mock

import grading_company_watch as watch


class GradingCompanyWatchV215Tests(unittest.TestCase):
    def test_psa_japan_new_service_price_and_turnaround_shape(self):
        text = (
            "サービスレベル スタンダード ￥9,980/枚（税込） 予定納期：100営業日 "
            "申告価格：￥150,000以下 申し込む "
            "プライオリティ ￥11,980/枚（税込） 予定納期：80営業日 "
            "申告価格：￥250,000以下 申し込む "
            "エクスプレス ￥29,980/枚（税込） 予定納期：25営業日 "
            "申告価格：￥400,000以下 申し込む"
        )
        rows = watch.parse_services("PSA", "JP", "JPY", text, "https://www.psacard.com/ja-JP/services/tradingcardgrading/grading")
        by_name = {row["name"]: row for row in rows}
        self.assertEqual(by_name["Standard"]["fee"], 9980)
        self.assertEqual(by_name["Standard"]["turnaround_business_days"], 100)
        self.assertEqual(by_name["Standard"]["max_declared_or_insured_value"], 150000)
        self.assertEqual(by_name["Priority"]["fee"], 11980)
        self.assertEqual(by_name["Priority"]["turnaround_business_days"], 80)
        self.assertEqual(by_name["Express"]["fee"], 29980)
        self.assertEqual(by_name["Express"]["turnaround_business_days"], 25)
        self.assertTrue(all(row["verified_official_source"] for row in rows))

    def test_service_add_remove_and_price_change_are_distinct(self):
        before = [
            {"name": "Regular", "fee": 11980, "availability": "open"},
            {"name": "Express", "fee": 22980, "turnaround_business_days": 25, "availability": "open"},
        ]
        after = [
            {"name": "Standard", "fee": 9980, "turnaround_business_days": 100, "availability": "open"},
            {"name": "Priority", "fee": 11980, "turnaround_business_days": 80, "availability": "open"},
            {"name": "Express", "fee": 29980, "turnaround_business_days": 25, "availability": "open"},
        ]
        changes = watch._service_changes("PSA", "psa-jp-pricing", before, after, "2026-09-10T00:00:00+00:00")
        pairs = {(row["type"], row["service"]) for row in changes}
        self.assertIn(("service_added", "Standard"), pairs)
        self.assertIn(("service_added", "Priority"), pairs)
        self.assertIn(("service_removed", "Regular"), pairs)
        self.assertIn(("service_changed", "Express"), pairs)
        express = next(row for row in changes if row["type"] == "service_changed" and row["service"] == "Express")
        self.assertEqual(express["changes"]["fee"], {"before": 22980, "after": 29980})

    def test_parser_collapse_does_not_invent_mass_removal(self):
        before = [
            {"name": "Bulk", "fee": 17}, {"name": "Economy", "fee": 20},
            {"name": "Standard", "fee": 55}, {"name": "Express", "fee": 100},
            {"name": "WalkThrough", "fee": 300},
        ]
        after = [{"name": "Express", "fee": 100}]
        changes = watch._service_changes("CGC", "cgc-pricing", before, after, "2026-09-10T00:00:00+00:00")
        self.assertFalse(any(row["type"] == "service_removed" for row in changes))

    def test_official_news_link_is_collected_but_external_link_is_not(self):
        raw = '''
        <a href="/ja-JP/articles/articleview/999/service-change">サービスレベル変更のお知らせ 2026/09/10</a>
        <a href="https://example.com/fake">PSA pricing event</a>
        '''
        rows = watch.extract_announcements(raw, "https://www.psacard.com/ja-JP/articles", "PSA", "psa-jp-news")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["announced_date"], "2026-09-10")
        self.assertTrue(rows[0]["url"].startswith("https://www.psacard.com/"))

    def test_cgc_fee_is_not_confused_with_max_declared_value(self):
        sample = (
            "Bulk Cards 25-card minimum Max. Value per Card (USD) $500 Fee Per Card (USD) $17 "
            "Current Turnaround (working days) 150 days Economy Max. Value per Card (USD) $1,000 "
            "Fee Per Card (USD) $20 Current Turnaround (working days) 90 days "
            "Standard Max. Value per Card (USD) $3,000 Fee Per Card (USD) $55 Current Turnaround (working days) 10 days"
        )
        rows=watch.parse_services('CGC','US','USD',sample,'https://www.cgccards.com/submit/services-fees/cgc-grading/?view=cards')
        by={row['name']:row for row in rows}
        self.assertEqual(by['Bulk']['fee'],17.0)
        self.assertEqual(by['Bulk']['max_declared_or_insured_value'],500.0)
        self.assertEqual(by['Bulk']['turnaround_business_days'],150)
        self.assertEqual(by['Economy']['fee'],20.0)
        self.assertEqual(by['Standard']['fee'],55.0)
        self.assertEqual(by['Bulk']['parser_version'],watch.PARSER_VERSION)

    def test_network_failure_retains_last_good_source(self):
        specs = ({"id": "psa-jp-pricing", "kind": "pricing", "market": "JP", "currency": "JPY",
                  "url": "https://www.psacard.com/ja-JP/services/tradingcardgrading/grading"},)
        previous = {
            "sources": {
                "psa-jp-pricing": {
                    "company": "PSA", "source_id": "psa-jp-pricing", "market": "JP", "currency": "JPY",
                    "url": specs[0]["url"], "signal_fingerprint": "last-good",
                    "services": [{"name": "Express", "fee": 29980, "currency": "JPY",
                                  "verified_official_source": True}],
                    "announcements": [], "verified_official_source": True,
                }
            },
            "announcements": [], "history": [],
        }
        with mock.patch.object(watch, "WATCH_SOURCES", {"PSA": specs}):
            data = watch.collect(previous, fetcher=mock.Mock(side_effect=OSError("temporary network failure")))
        source = data["sources"]["psa-jp-pricing"]
        self.assertEqual(source["status"], "degraded")
        self.assertEqual(source["services"][0]["fee"], 29980)
        self.assertTrue(data["companies"]["PSA"]["markets"]["JP"]["retained_last_good"])

    def test_repeated_failure_never_promotes_unverified_source(self):
        specs = ({"id": "psa-jp-pricing", "kind": "pricing", "market": "JP", "currency": "JPY",
                  "url": "https://www.psacard.com/ja-JP/services/tradingcardgrading/grading"},)
        previous = {"sources": {"psa-jp-pricing": {
            "company": "PSA", "source_id": "psa-jp-pricing", "kind": "pricing",
            "market": "JP", "currency": "JPY", "url": specs[0]["url"],
            "status": "degraded", "services": [], "announcements": [],
            "verified_official_source": False,
        }}, "announcements": [], "history": []}
        with mock.patch.object(watch, "WATCH_SOURCES", {"PSA": specs}):
            data = watch.collect(previous, fetcher=mock.Mock(side_effect=OSError("still blocked")))
        self.assertFalse(data["sources"]["psa-jp-pricing"]["verified_official_source"])

    def test_pricing_fetch_without_verified_services_is_degraded(self):
        specs = ({"id": "tag-pricing", "kind": "pricing", "market": "US", "currency": "USD",
                  "url": "https://taggrading.com/pages/pricing"},)
        html = "<html><body>TAG official grading pricing page is reachable but the dynamic price table is unavailable in this response.</body></html>"
        with mock.patch.object(watch, "WATCH_SOURCES", {"TAG": specs}):
            data = watch.collect({}, fetcher=lambda _url: html)
        source = data["sources"]["tag-pricing"]
        self.assertEqual("degraded", source["status"])
        self.assertIn("zero verified services", source["last_error"])
        self.assertFalse(source["verified_official_source"])

    def test_initial_baseline_does_not_claim_every_current_service_changed(self):
        specs = ({"id": "psa-jp-pricing", "kind": "pricing", "market": "JP", "currency": "JPY",
                  "url": "https://www.psacard.com/ja-JP/services/tradingcardgrading/grading"},)
        html = (
            "<html><body>PSA公式トレーディングカード鑑定サービス 料金と納期のご案内。"
            "スタンダード ￥9,980 予定納期：100営業日 申告価格：￥150,000以下 申し込む。"
            "サービス内容、申告価格、予定納期は公式ページの最新表示を確認してください。"
            "料金、受付状況、サービスレベルの変更はこの公式案内に掲載されます。</body></html>"
        )
        with mock.patch.object(watch, "WATCH_SOURCES", {"PSA": specs}):
            data = watch.collect({}, fetcher=lambda _url: html)
        self.assertEqual(data["recent_changes"], [])
        self.assertEqual(data["history"], [])
        self.assertEqual(data["sources"]["psa-jp-pricing"]["services"][0]["name"], "Standard")

    def test_new_source_is_baseline_even_when_other_sources_have_history(self):
        specs = ({"id": "psa-jp-news", "kind": "news", "market": "JP", "currency": "JPY",
                  "url": "https://www.psacard.com/ja-JP/articles"},)
        previous = {
            "sources": {
                "bgs-pricing": {"verified_official_source": True, "announcements": [], "services": []}
            },
            "announcements": [{"company": "BGS", "source_id": "bgs-pricing", "title": "old",
                               "url": "https://www.beckett.com/grading", "verified_official_source": True}],
            "history": [],
        }
        raw = (
            "<html><body>PSA公式ニュース、サービスレベル、料金、納期、受付状況に関する最新のお知らせ一覧です。"
            "<a href='/ja-JP/articles/articleview/999/service-change'>サービスレベル変更のお知らせ 2026/09/10</a>"
            "公式発表のみを掲載し、詳細は各記事本文で確認できます。</body></html>"
        )
        with mock.patch.object(watch, "WATCH_SOURCES", {"PSA": specs}):
            data = watch.collect(previous, fetcher=lambda _url: raw)
        self.assertEqual(data["recent_changes"], [])
        self.assertEqual(len(data["announcements"]), 2)

    def test_policy_never_allows_community_posts_to_write_verified_facts(self):
        with mock.patch.object(watch, "WATCH_SOURCES", {}):
            data = watch.collect({})
        self.assertTrue(data["policy"]["official_sources_only"])
        self.assertTrue(data["policy"]["community_posts_are_leads_only"])
        self.assertFalse(data["policy"]["automatic_source_code_mutation"])


    def test_tag_official_collection_layout_parses_price_and_stock_per_tier(self):
        source = "https://taggrading.com/collections/grading-services-official"
        text = (
            "TAG GRADING SERVICES OFFICIAL "
            "Quick buy GRADING | BASIC From $22.00 USD Sold Out "
            "Quick buy GRADING | STANDARD From $39.00 USD Sold Out "
            "Quick buy GRADING | EXPRESS $79.00 USD Sold Out "
            "Quick buy GRADING | PRIORITY $149.00 USD "
            "Quick buy GRADING | WALKTHROUGH $299.00 USD"
        )
        rows = watch.parse_services("TAG", "US", "USD", text, source)
        by = {row["name"]: row for row in rows}
        self.assertEqual(set(by), {"Basic", "Standard", "Express", "Priority", "Walkthrough"})
        self.assertEqual(by["Basic"]["fee"], 22.0)
        self.assertEqual(by["Standard"]["fee"], 39.0)
        self.assertEqual(by["Express"]["fee"], 79.0)
        self.assertEqual(by["Priority"]["fee"], 149.0)
        self.assertEqual(by["Walkthrough"]["fee"], 299.0)
        self.assertEqual(by["Basic"]["availability"], "paused")
        self.assertEqual(by["Standard"]["availability"], "paused")
        self.assertEqual(by["Express"]["availability"], "paused")
        self.assertEqual(by["Priority"]["availability"], "open")
        self.assertEqual(by["Walkthrough"]["availability"], "open")
        self.assertTrue(all(row["source"] == source for row in rows))

    def test_tag_pricing_source_uses_official_service_collection_without_widening_hosts(self):
        spec = next(row for row in watch.WATCH_SOURCES["TAG"] if row["id"] == "tag-pricing")
        self.assertEqual(spec["url"], "https://taggrading.com/collections/grading-services-official")
        self.assertTrue(watch._source_host_allowed(spec["url"]))
        self.assertNotIn("help.taggrading.com", watch.ALLOWED_HOSTS)


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


    def test_bgs_current_layout_parses_base_variants_and_tier_local_availability(self):
        source = "https://www.beckett.com/grading"
        text = (
            "Base 75+ business days $14.95 per card $3 fee for any 10s where subgrades are added "
            "Sold Out Without Subgrades Notify me $17.95 per card Sold Out Subgrades Notify me "
            "Standard 45 business days $34.95 per card Sold Out Subgrades Notify me "
            "Express 15 business days $79.95 per card Subgrades Submit Now "
            "Priority 5 business days $124.95 per card Subgrades Submit Now"
        )
        rows = watch.parse_services("BGS", "US", "USD", text, source)
        by = {row["name"]: row for row in rows}
        self.assertEqual(set(by), {"Base", "Base + Subgrades", "Standard", "Express", "Priority"})
        self.assertEqual(by["Base"]["fee"], 14.95)
        self.assertEqual(by["Base + Subgrades"]["fee"], 17.95)
        self.assertEqual(by["Standard"]["fee"], 34.95)
        self.assertEqual(by["Express"]["fee"], 79.95)
        self.assertEqual(by["Priority"]["fee"], 124.95)
        self.assertEqual(by["Base"]["turnaround_business_days"], 75)
        self.assertEqual(by["Standard"]["turnaround_business_days"], 45)
        self.assertEqual(by["Express"]["turnaround_business_days"], 15)
        self.assertEqual(by["Priority"]["turnaround_business_days"], 5)
        self.assertEqual(by["Base"]["availability"], "paused")
        self.assertEqual(by["Base + Subgrades"]["availability"], "paused")
        self.assertEqual(by["Standard"]["availability"], "paused")
        self.assertEqual(by["Express"]["availability"], "open")
        self.assertEqual(by["Priority"]["availability"], "open")

    def test_bgs_partial_layout_fails_closed_instead_of_publishing_mixed_tiers(self):
        text = "Base 75+ business days $14.95 per card Sold Out Without Subgrades $17.95 per card Sold Out Subgrades"
        self.assertEqual(watch.parse_services("BGS", "US", "USD", text, "https://www.beckett.com/grading"), [])

    def test_psa_overlapping_aliases_do_not_duplicate_longer_tiers(self):
        source = "https://www.psacard.com/services/t"
        text = (
            "Currently Unavailable Value Bulk Max Insured Value: $500 "
            "Currently Unavailable Value Max Insured Value: $500 "
            "Currently Unavailable Value Plus Max Insured Value: $500 "
            "Currently Unavailable Value Max Max Insured Value: $1,000 "
            "Regular $79.99/Card Max Insured Value: $1,500 Estimated Turnaround Time: 70 - 80 Business Days Get Started "
            "Express $149.00/Card Max Insured Value: $2,500 Estimated Turnaround Time: 20 - 30 Business Days Get Started "
            "Super Express $299.00/Card Max Insured Value: $5,000 Estimated Turnaround Time: 10 Business Days Get Started"
        )
        rows = watch.parse_services("PSA", "US", "USD", text, source)
        by = {row["name"]: row for row in rows}
        self.assertEqual(by["Value Bulk"]["max_declared_or_insured_value"], 500.0)
        self.assertEqual(by["Value"]["max_declared_or_insured_value"], 500.0)
        self.assertEqual(by["Value Plus"]["max_declared_or_insured_value"], 500.0)
        self.assertEqual(by["Value Max"]["max_declared_or_insured_value"], 1000.0)
        self.assertEqual(by["Express"]["fee"], 149.0)
        self.assertEqual(by["Super Express"]["fee"], 299.0)


    def test_source_failure_classes_keep_blocked_sources_distinct(self):
        class Blocked(Exception):
            code = 403

        class Limited(Exception):
            code = 429

        self.assertEqual(watch._source_failure_class(Blocked("forbidden")), "http_forbidden")
        self.assertEqual(watch._source_failure_class(Limited("rate limited")), "rate_limited")
        self.assertEqual(watch._source_failure_class(ValueError("unapproved host")), "redirect_unapproved_host")
        self.assertEqual(
            watch._source_failure_class(ValueError("pricing parser yielded zero verified services")),
            "parser_no_verified_services",
        )
        self.assertEqual(watch._source_failure_class(OSError("network down")), "source_error")

    def test_failure_class_is_persisted_in_source_and_health_rows(self):
        class Blocked(Exception):
            code = 403

        def fail(_url):
            raise Blocked("forbidden")

        out = watch.collect({}, fail)
        self.assertTrue(out["sources"])
        self.assertTrue(all(row.get("failure_class") == "http_forbidden" for row in out["sources"].values()))
        health = [row for company in out["companies"].values() for row in company["source_health"]]
        self.assertTrue(health)
        self.assertTrue(all(row.get("failure_class") == "http_forbidden" for row in health))


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


if __name__ == "__main__":
    unittest.main()
