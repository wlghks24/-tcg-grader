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


if __name__ == "__main__":
    unittest.main()
