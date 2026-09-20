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


if __name__ == "__main__":
    unittest.main()
