#!/usr/bin/env python3
"""V518: report-only classification of failed official grading sources (no gate bypass)."""
from __future__ import annotations

import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path

import collection_verification_gate as gate


class GradingCompanyFailureClassV518Tests(unittest.TestCase):
    def _audit(self, errors: list[tuple[str, str]]):
        now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
        hosts = {
            "PSA": "https://www.psacard.com/services/tradingcardgrading",
            "BGS": "https://www.beckett.com/grading",
            "CGC": "https://www.cgccards.com/news/",
            "TAG": "https://taggrading.com/",
            "BRG": "https://break.co.kr/",
        }
        sources = {
            f"{company.lower()}-{index}": {
                "company": company, "status": "ok", "kind": "pricing",
                "market": "US", "url": url,
            }
            for company, url in hosts.items()
            for index in range(2)
        }
        # All PSA sources are degraded; another provider's health must not
        # erase its failures or make the report publishable.
        for index, (error, recorded) in enumerate(errors):
            sources[f"psa-{index}"] = {
                "company": "PSA", "status": "degraded",
                "kind": "pricing", "market": "US", "url": hosts["PSA"],
                "last_error": error, "failure_class": recorded,
                "verified_official_source": True,
                "services": [{"name": "last good, not fresh", "fee": 40}],
            }
        if len(errors) == 1:
            sources["psa-1"] = dict(sources["psa-0"])
        data = {
            "schema_version": 1,
            "checked_at": now.isoformat(),
            "policy": {
                "official_sources_only": True,
                "community_posts_are_leads_only": True,
                "automatic_source_code_mutation": False,
                "last_good_retained_on_failure": True,
            },
            "companies": {company: {} for company in hosts},
            "sources": sources,
            "recent_changes": [],
        }
        with tempfile.TemporaryDirectory() as td:
            (Path(td) / "grading_company_updates.json").write_text(
                json.dumps(data, ensure_ascii=False), encoding="utf-8"
            )
            findings: list[dict] = []
            metrics = gate._audit_grading_companies(Path(td), now, findings)
        finding = next(x for x in findings if x["code"] == "GRADING_COMPANY_NO_HEALTHY_SOURCE")
        return finding, metrics, findings

    def test_blocked_and_transient_errors_are_not_unclassified(self):
        cases = [
            ("HTTPError: status 403", "unclassified", "SOURCE_BLOCKED"),
            ("HTTPError: status 429", "HEALTHY", "RATE_LIMIT_PRESSURE"),
            ("HTTPError: status 500", "", "SOURCE_TRANSIENT"),
        ]
        for error, recorded, expected in cases:
            with self.subTest(error=error):
                finding, metrics, _ = self._audit([(error, recorded)])
                sample = finding["degraded_samples_by_company"]["PSA"][0]
                self.assertEqual(sample["failure_class"], expected)
                self.assertEqual(sample["error"], error)
                self.assertEqual(sample["company"], "PSA")
                self.assertEqual(finding["severity"], "high")
                self.assertEqual(metrics["grading_companies_with_healthy_source"], 4)

    def test_explicit_maintenance_and_unresolved_remain_honest(self):
        samples = [
            ("maintenance source unchanged", "provider_maintenance_redirect"),
            ("unexpected page body", ""),
        ]
        finding, _metrics, _ = self._audit(samples)
        classes = [
            row["failure_class"]
            for row in finding["degraded_samples_by_company"]["PSA"]
        ]
        self.assertEqual(classes, ["provider_maintenance_redirect", "unclassified"])

    def test_last_good_does_not_promote_degraded_to_healthy(self):
        finding, metrics, findings = self._audit(
            [("HTTPError: status 403", "HEALTHY")]
        )
        self.assertEqual(finding["severity"], "high")
        self.assertEqual(metrics["healthy_grading_sources"], 8)
        self.assertEqual(metrics["degraded_grading_sources"], 2)
        self.assertFalse(any(x["code"] == "INVALID_GRADING_SOURCE" for x in findings))
        self.assertEqual(
            finding["degraded_samples_by_company"]["PSA"][0]["failure_class"],
            "SOURCE_BLOCKED",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
