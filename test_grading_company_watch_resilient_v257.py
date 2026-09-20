#!/usr/bin/env python3
from __future__ import annotations

import copy
import unittest
from unittest import mock

import grading_company_watch_resilient as resilient


class GradingCompanyWatchResilientV257Tests(unittest.TestCase):
    def _degraded_payload(self):
        return {
            "schema_version": 1,
            "summary": {"companies": 5, "sources": 11, "healthy_sources": 8, "degraded_sources": 3},
            "companies": {
                "BGS": {
                    "markets": {},
                    "source_health": [
                        {"source_id": "bgs-pricing", "status": "degraded", "url": "https://www.beckett.com/grading"},
                        {"source_id": "bgs-news", "status": "degraded", "url": "https://www.beckett.com/news/"},
                    ],
                }
            },
            "sources": {
                "bgs-pricing": {
                    "company": "BGS", "source_id": "bgs-pricing", "kind": "pricing", "market": "US",
                    "currency": "USD", "url": "https://www.beckett.com/grading", "status": "degraded",
                    "last_error": "BeckettMaintenanceRedirect: canonical Beckett source temporarily redirected to maintenance.beckett.com",
                    "services": [{"name": "Base", "fee": 20, "verified_official_source": True}],
                    "verified_official_source": True,
                },
                "bgs-news": {
                    "company": "BGS", "source_id": "bgs-news", "kind": "news", "market": "GLOBAL",
                    "currency": "USD", "url": "https://www.beckett.com/news/", "status": "degraded",
                    "last_error": "BeckettMaintenanceRedirect: canonical Beckett source temporarily redirected to maintenance.beckett.com",
                    "services": [], "verified_official_source": True,
                },
            },
            "recent_changes": [], "announcements": [], "history": [],
        }

    @staticmethod
    def _tag_fallback_html():
        return """
        <html><body>
          TAG Grading Services Official
          GRADING | BASIC From $22.00 USD Sold Out
          GRADING | STANDARD From $39.00 USD Sold Out
          GRADING | EXPRESS From $79.00 USD Sold Out
          GRADING | PRIORITY From $149.00 USD Available
          GRADING | WALKTHROUGH From $299.00 USD Available
        </body></html>
        """ + (" verified official grading services " * 30)

    def test_maintenance_status_is_separate_and_never_promotes_price_facts(self):
        payload = self._degraded_payload()
        status = {
            "company": "BGS", "source_id": resilient.STATUS_SOURCE_ID, "kind": "status", "market": "US",
            "currency": "USD", "url": resilient.BGS_CANONICAL_STATUS_URL,
            "effective_url": "https://maintenance.beckett.com/", "status": "ok",
            "checked_at": "2026-09-20T00:00:00+00:00", "signal_fingerprint": "a" * 64,
            "services": [], "announcements": [], "maintenance_mode": True,
            "available_service_labels": ["Base", "Standard", "Express"],
            "verified_official_source": True, "parser_version": 2,
            "fact_scope": "service_availability_status_only_no_price_promotion",
        }
        with mock.patch.object(resilient.base, "collect", return_value=copy.deepcopy(payload)), \
             mock.patch.object(resilient, "_maintenance_status", return_value=status):
            data = resilient.collect({})
        self.assertEqual(data["sources"]["bgs-pricing"]["status"], "degraded")
        self.assertEqual(data["sources"]["bgs-pricing"]["services"][0]["fee"], 20)
        self.assertEqual(data["sources"]["bgs-pricing"]["failure_class"], "planned_maintenance")
        self.assertEqual(data["sources"][resilient.STATUS_SOURCE_ID]["services"], [])
        self.assertFalse(data["resilience"]["bgs_maintenance_status"]["price_facts_promoted"])
        self.assertTrue(any(row.get("source_id") == resilient.STATUS_SOURCE_ID and row.get("status") == "ok"
                            for row in data["companies"]["BGS"]["source_health"]))

    def test_status_trust_is_anchored_at_canonical_beckett_redirect(self):
        html = "<html><body>Beckett digital upgrade. Temporary Submission Form. Base Standard Express services available.</body></html>" + (" x" * 120)
        with mock.patch.object(resilient, "_request", return_value=(html, "https://maintenance.beckett.com/")):
            row = resilient._maintenance_status()
        self.assertEqual(row["url"], "https://www.beckett.com/grading")
        self.assertEqual(row["effective_url"], "https://maintenance.beckett.com/")
        self.assertEqual(row["services"], [])
        self.assertTrue(row["verified_official_source"])
        self.assertIn("Base", row["available_service_labels"])

    def test_nonmaintenance_redirect_is_not_promoted(self):
        html = "Beckett Temporary Submission Form Base Standard Express " + ("x" * 300)
        with mock.patch.object(resilient, "_request", return_value=(html, "https://www.beckett.com/grading")):
            with self.assertRaises(ValueError):
                resilient._maintenance_status()

    def test_incomplete_maintenance_page_is_not_promoted(self):
        html = "Beckett maintenance" + ("x" * 300)
        with mock.patch.object(resilient, "_request", return_value=(html, "https://maintenance.beckett.com/")):
            with self.assertRaises(ValueError):
                resilient._maintenance_status()

    def test_transaction_request_cache_reuses_exact_url_without_persisting_between_runs(self):
        calls = []

        def request(url):
            calls.append(url)
            return ("<html>ok</html>", url)

        cached, stats = resilient._make_cached_requester(request)
        first = cached("https://www.beckett.com/grading")
        second = cached("https://www.beckett.com/grading")
        self.assertEqual(first, second)
        self.assertEqual(calls, ["https://www.beckett.com/grading"])
        self.assertEqual(stats["network_calls"], 1)
        self.assertEqual(stats["cache_hits"], 1)

        # A new transaction gets a new cache and therefore performs a fresh check.
        cached_next, next_stats = resilient._make_cached_requester(request)
        cached_next("https://www.beckett.com/grading")
        self.assertEqual(len(calls), 2)
        self.assertEqual(next_stats["network_calls"], 1)
        self.assertEqual(next_stats["cache_hits"], 0)

    def test_tag_official_fallback_parses_expected_service_fees(self):
        html = self._tag_fallback_html()
        row = resilient._tag_pricing_fallback(
            requester=lambda _url: (html, "https://taggrading.com/collections/grading-services-official")
        )
        by_name = {item["name"]: item for item in row["services"]}
        self.assertEqual(by_name["Basic"]["fee"], 22.0)
        self.assertEqual(by_name["Standard"]["fee"], 39.0)
        self.assertEqual(by_name["Express"]["fee"], 79.0)
        self.assertEqual(by_name["Priority"]["fee"], 149.0)
        self.assertEqual(by_name["Walkthrough"]["fee"], 299.0)
        self.assertTrue(all(item.get("verified_official_source") is True for item in row["services"]))
        self.assertEqual(row["fact_scope"], "official_pricing_and_availability")

    def test_tag_official_fallback_rejects_partial_or_wrong_host_pages(self):
        partial = "TAG GRADING | PRIORITY From $149.00 USD" + (" x" * 200)
        with self.assertRaises(ValueError):
            resilient._tag_pricing_fallback(
                requester=lambda _url: (partial, "https://taggrading.com/collections/grading-services-official")
            )
        with self.assertRaises(ValueError):
            resilient._tag_pricing_fallback(
                requester=lambda _url: (self._tag_fallback_html(), "https://example.com/not-tag")
            )

    def test_degraded_tag_primary_installs_verified_official_pricing_fallback(self):
        payload = {
            "schema_version": 1,
            "summary": {"companies": 5, "sources": 2, "healthy_sources": 1, "degraded_sources": 1},
            "companies": {
                "TAG": {
                    "markets": {},
                    "source_health": [
                        {"source_id": "tag-pricing", "status": "degraded", "url": "https://taggrading.com/pages/pricing"},
                        {"source_id": "tag-home", "status": "ok", "url": "https://taggrading.com/"},
                    ],
                }
            },
            "sources": {
                "tag-pricing": {
                    "company": "TAG", "source_id": "tag-pricing", "kind": "pricing", "market": "US",
                    "currency": "USD", "url": "https://taggrading.com/pages/pricing", "status": "degraded",
                    "services": [], "announcements": [], "verified_official_source": True,
                    "last_error": "ValueError: pricing parser yielded zero verified services",
                },
                "tag-home": {
                    "company": "TAG", "source_id": "tag-home", "kind": "news", "market": "GLOBAL",
                    "currency": "USD", "url": "https://taggrading.com/", "status": "ok",
                    "services": [], "announcements": [], "verified_official_source": True,
                },
            },
            "recent_changes": [], "announcements": [], "history": [],
        }
        html = self._tag_fallback_html()
        with mock.patch.object(resilient.base, "collect", return_value=copy.deepcopy(payload)):
            data = resilient.collect(
                {}, requester=lambda _url: (html, "https://taggrading.com/collections/grading-services-official")
            )
        fallback = data["sources"][resilient.TAG_FALLBACK_SOURCE_ID]
        self.assertEqual(fallback["status"], "ok")
        self.assertEqual(len(data["companies"]["TAG"]["markets"]["US"]["services"]), 5)
        self.assertTrue(data["resilience"]["tag_pricing_fallback"]["price_facts_promoted"])
        self.assertEqual(data["summary"]["healthy_pricing_sources"], 1)
        self.assertEqual(data["summary"]["grading_companies_with_healthy_pricing"], 1)
        self.assertNotIn("TAG", data["summary"]["pricing_degraded_companies"])


if __name__ == "__main__":
    unittest.main()
