from __future__ import annotations

import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path

import auto_update_all
import collection_verification_gate as gate
import grading_company_watch


class CollectionVerificationGateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.now = dt.datetime(2026, 9, 6, 0, 0, tzinfo=dt.timezone.utc)

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, name, value):
        (self.root / name).write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")

    def valid_grading_fixture(self):
        stamp = self.now.isoformat(timespec="seconds")
        hosts = {
            "PSA": "psacard.com",
            "BGS": "beckett.com",
            "CGC": "cgccards.com",
            "TAG": "taggrading.com",
            "BRG": "break.co.kr",
        }
        sources = {}
        for company, host in hosts.items():
            for index in range(2):
                sources[f"{company.lower()}-{index}"] = {
                    "company": company,
                    "url": f"https://{host}/official-{index}",
                    "status": "healthy",
                    "checked_at": stamp,
                }
        return {
            "schema_version": 1,
            "checked_at": stamp,
            "companies": {company: {} for company in hosts},
            "sources": sources,
            "recent_changes": [],
            "policy": {
                "official_sources_only": True,
                "community_posts_are_leads_only": True,
                "automatic_source_code_mutation": False,
                "last_good_retained_on_failure": True,
            },
        }

    def valid_fixture(self):
        stamp = self.now.isoformat(timespec="seconds")
        self.write("source_collection_stats.json", {"updated_at": stamp, "sources": {"official": {"runs": 1}}})
        self.write("adaptive_collection_stats.json", {"updated_at": stamp, "jobs": {"release": {"runs": 1}}})
        self.write("market_prices.json", {"updated_at": stamp, "entries": {"KR|테스트|BOX": {"display": "₩10,000", "source": "https://example.com/item", "source_date": "2026-09-06"}}})
        self.write("releases.json", {"items": [{"game": "Pokémon", "region": "JP", "name": "Test", "release_date": "2026-09-06", "source": "https://example.com/release"}]})
        self.write("promo_events.json", {"items": [{"region": "KR", "category": "promo", "name_ko": "Test", "source": "https://example.com/event", "source_grade": "official"}]})
        self.write("grading_company_updates.json", self.valid_grading_fixture())
        self.write("auto_update_report.json", {"results": [{"file": name, "ok": True, "remaining_collection_errors": []} for name in gate.MANDATORY_OUTPUT_FILES]})

    def test_mandatory_output_contract_matches_auto_update_jobs(self):
        self.assertEqual(
            tuple(job[2] for job in auto_update_all.JOBS),
            gate.MANDATORY_OUTPUT_FILES,
        )
        self.assertEqual(len(gate.MANDATORY_OUTPUT_FILES), 8)
        self.assertEqual(grading_company_watch.ALLOWED_HOSTS, gate.GRADING_ALLOWED_HOSTS)

    def test_valid_collection_passes(self):
        self.valid_fixture()
        report = gate.verify(self.root, now=self.now)
        self.assertEqual("pass", report["status"])
        self.assertEqual(0, report["counts"]["critical"])
        self.assertEqual(8, report["metrics"]["critical_outputs_seen"])
        self.assertEqual(5, report["metrics"]["grading_companies_with_healthy_source"])

    def test_topic_collection_attempts_are_distinct_from_zero_results(self):
        self.valid_fixture()
        self.write("promo_events.json", {
            "items": [{"region": "KR", "category": "promo", "name_ko": "Test",
                       "source": "https://example.com/event", "source_grade": "official"}],
            "social_topic_expected_cells": 216,
            "social_topic_attempted_cells": 216,
            "social_topic_successful_cells": 210,
            "social_topic_failed_cells": ["나루토 카드/US/movie"],
            "social_topic_undiscovered_cells": [f"cell-{i}" for i in range(216)],
        })
        report = gate.verify(self.root, now=self.now)
        self.assertFalse(any(x["code"] == "INCOMPLETE_EVENT_TOPIC_COLLECTION_ATTEMPTS" for x in report["findings"]))
        self.assertEqual(216, report["metrics"]["attempted_event_topic_cells"])
        self.assertEqual(216, report["metrics"]["undiscovered_event_topic_cells"])

    def test_missing_topic_collection_attempt_is_degraded(self):
        self.valid_fixture()
        self.write("promo_events.json", {
            "items": [{"region": "KR", "category": "promo", "name_ko": "Test",
                       "source": "https://example.com/event", "source_grade": "official"}],
            "social_topic_expected_cells": 216,
            "social_topic_attempted_cells": 215,
            "social_topic_successful_cells": 215,
        })
        report = gate.verify(self.root, now=self.now)
        self.assertEqual("degraded", report["status"])
        self.assertTrue(any(x["code"] == "INCOMPLETE_EVENT_TOPIC_COLLECTION_ATTEMPTS" for x in report["findings"]))

    def test_empty_source_health_fails_closed(self):
        self.valid_fixture()
        self.write("source_collection_stats.json", {"updated_at": self.now.isoformat(), "sources": {}})
        report = gate.verify(self.root, now=self.now)
        self.assertEqual("fail_closed", report["status"])
        self.assertTrue(any(x["code"] == "EMPTY_SOURCE_HEALTH" for x in report["findings"]))

    def test_stale_health_is_degraded(self):
        self.valid_fixture()
        old = self.now - dt.timedelta(hours=2)
        self.write("source_collection_stats.json", {"updated_at": old.isoformat(), "sources": {"a": {}}})
        report = gate.verify(self.root, now=self.now, max_health_age_seconds=900)
        self.assertEqual("degraded", report["status"])
        self.assertTrue(any(x["code"] == "STALE_COLLECTION_STATE" for x in report["findings"]))

    def test_invalid_market_provenance_is_degraded(self):
        self.valid_fixture()
        self.write("market_prices.json", {"updated_at": self.now.isoformat(), "entries": {"KR|테스트|BOX": {"display": "₩10,000", "source": "http://localhost/item"}}})
        report = gate.verify(self.root, now=self.now)
        self.assertEqual("degraded", report["status"])
        self.assertTrue(any(x["code"] == "INVALID_MARKET_ENTRY" for x in report["findings"]))

    def test_missing_critical_output_report_fails_closed(self):
        self.valid_fixture()
        self.write("auto_update_report.json", {"results": []})
        report = gate.verify(self.root, now=self.now)
        self.assertEqual("fail_closed", report["status"])
        self.assertEqual(len(gate.MANDATORY_OUTPUT_FILES), sum(x["code"] == "CRITICAL_OUTPUT_NOT_REPORTED" for x in report["findings"]))

    def test_429_is_degraded_not_bypassed(self):
        self.valid_fixture()
        rows = [{"file": name, "ok": True, "remaining_collection_errors": []} for name in gate.MANDATORY_OUTPUT_FILES]
        rows[0] = {"file": "releases.json", "ok": False, "remaining_collection_errors": ["official: HTTPError: status 429; Retry-After 120s"]}
        self.write("auto_update_report.json", {"results": rows})
        report = gate.verify(self.root, now=self.now)
        self.assertEqual("degraded", report["status"])
        finding = next(x for x in report["findings"] if x["code"] == "DEGRADED_COLLECTION_OUTPUT")
        self.assertEqual(1, finding["blocked_403_429"])
        self.assertFalse(report["safety"]["bypass_403_429"])

    def test_hard_collection_failure_fails_closed(self):
        self.valid_fixture()
        rows = [{"file": name, "ok": True, "remaining_collection_errors": []} for name in gate.MANDATORY_OUTPUT_FILES]
        rows[2] = {"file": "market_prices.json", "ok": False, "remaining_collection_errors": ["parser schema mismatch"]}
        self.write("auto_update_report.json", {"results": rows})
        report = gate.verify(self.root, now=self.now)
        self.assertEqual("fail_closed", report["status"])
        self.assertTrue(any(x["code"] == "HARD_COLLECTION_FAILURE" for x in report["findings"]))

    def test_grading_snapshot_rejects_unapproved_source_host(self):
        self.valid_fixture()
        payload = self.valid_grading_fixture()
        payload["sources"]["psa-0"]["url"] = "https://example.com/not-official"
        self.write("grading_company_updates.json", payload)
        report = gate.verify(self.root, now=self.now)
        self.assertEqual("fail_closed", report["status"])
        self.assertTrue(any(x["code"] == "INVALID_GRADING_SOURCE" and "unapproved_source_host" in x.get("reasons", []) for x in report["findings"]))

    def test_grading_company_without_healthy_source_is_degraded(self):
        self.valid_fixture()
        payload = self.valid_grading_fixture()
        for row in payload["sources"].values():
            if row["company"] == "BGS":
                row["status"] = "degraded"
                row["error"] = "HTTPError: status 503; Retry-After 60s"
        self.write("grading_company_updates.json", payload)
        report = gate.verify(self.root, now=self.now)
        self.assertEqual("degraded", report["status"])
        finding = next(x for x in report["findings"] if x["code"] == "GRADING_COMPANY_NO_HEALTHY_SOURCE")
        self.assertEqual(["BGS"], finding["companies"])

    def test_bad_release_region_is_degraded(self):
        self.valid_fixture()
        self.write("releases.json", {"items": [{"game": "Pokémon", "region": "XX", "name": "Bad", "source": "https://example.com/r"}]})
        report = gate.verify(self.root, now=self.now)
        self.assertEqual("degraded", report["status"])
        self.assertTrue(any(x["code"] == "INVALID_RELEASE_ROW" for x in report["findings"]))

    def test_asia_promo_event_is_valid_without_widening_release_regions(self):
        self.valid_fixture()
        self.write("promo_events.json", {"items": [{
            "game": "포켓몬 카드",
            "region": "ASIA",
            "category": "promo",
            "name_ko": "Pokémon RUN 30 완주자 피카츄 프로모 카드",
            "source": "https://tw.portal-pokemon.com/30th/topics/20260902_02/?lang=en",
            "source_grade": "official",
        }]})
        report = gate.verify(self.root, now=self.now)
        self.assertEqual("pass", report["status"])
        self.assertEqual(0, report["metrics"]["invalid_promo_event_items"])
        self.assertNotIn("ASIA", gate.ALLOWED_REGIONS)
        self.assertIn("ASIA", gate.ALLOWED_EVENT_REGIONS)

    def test_asia_release_remains_invalid(self):
        self.valid_fixture()
        self.write("releases.json", {"items": [{
            "game": "Pokémon",
            "region": "ASIA",
            "name": "Must remain event-only",
            "source": "https://example.com/release",
        }]})
        report = gate.verify(self.root, now=self.now)
        self.assertEqual("degraded", report["status"])
        self.assertEqual(1, report["metrics"]["invalid_release_items"])
        self.assertTrue(any(
            x["code"] == "INVALID_RELEASE_ROW" and "bad_region" in x.get("reasons", [])
            for x in report["findings"]
        ))

    def test_global_release_scope_is_valid(self):
        self.valid_fixture()
        self.write("releases.json", {"items": [{"game": "NARUTO", "region": "GLOBAL", "name": "NARUTO CARD GAME", "release_window": "2027 summer", "source": "https://example.com/naruto"}]})
        report = gate.verify(self.root, now=self.now)
        self.assertEqual("pass", report["status"])
        self.assertEqual(0, report["metrics"]["invalid_release_items"])


if __name__ == "__main__":
    unittest.main()