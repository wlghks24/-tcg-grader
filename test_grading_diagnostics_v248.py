import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path

import collection_verification_gate as gate


class GradingDiagnosticsV248Tests(unittest.TestCase):
    def _snapshot(self, now: dt.datetime) -> dict:
        sources = {}
        for idx in range(20):
            sources[f"bgs-degraded-{idx}"] = {
                "company": "BGS",
                "status": "degraded",
                "market": "US",
                "kind": "pricing" if idx % 2 == 0 else "news",
                "url": "https://www.beckett.com/grading",
                "failure_class": "provider_maintenance_redirect",
                "last_error": f"maintenance-{idx}",
            }
        for idx in range(2):
            sources[f"psa-degraded-{idx}"] = {
                "company": "PSA",
                "status": "degraded",
                "market": "US",
                "kind": "pricing",
                "url": "https://www.psacard.com/services/tradingcardgrading",
                "last_error": f"HTTPError: status 403 sample-{idx}",
            }
        sources.update({
            "cgc-ok": {"company": "CGC", "status": "ok", "market": "US", "kind": "pricing", "url": "https://www.cgccards.com/news/"},
            "tag-ok": {"company": "TAG", "status": "ok", "market": "US", "kind": "pricing", "url": "https://taggrading.com/"},
            "brg-ok": {"company": "BRG", "status": "ok", "market": "KR", "kind": "pricing", "url": "https://break.co.kr/"},
        })
        return {
            "schema_version": 1,
            "checked_at": now.isoformat(),
            "policy": {
                "official_sources_only": True,
                "community_posts_are_leads_only": True,
                "automatic_source_code_mutation": False,
                "last_good_retained_on_failure": True,
            },
            "companies": {name: {} for name in gate.EXPECTED_GRADING_COMPANIES},
            "sources": sources,
            "recent_changes": [],
        }

    def _audit(self):
        now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "grading_company_updates.json").write_text(
                json.dumps(self._snapshot(now), ensure_ascii=False), encoding="utf-8"
            )
            findings = []
            metrics = gate._audit_grading_companies(root, now, findings)
        finding = next(row for row in findings if row.get("code") == "GRADING_COMPANY_NO_HEALTHY_SOURCE")
        return finding, findings, metrics

    def test_noisy_provider_cannot_starve_other_company_samples(self):
        finding, _findings, metrics = self._audit()
        self.assertEqual(finding["companies"], ["BGS", "PSA"])
        grouped = finding["degraded_samples_by_company"]
        self.assertEqual(set(grouped), {"BGS", "PSA"})
        self.assertEqual(len(grouped["BGS"]), 5)
        self.assertEqual(len(grouped["PSA"]), 2)
        self.assertEqual(finding["degraded_sample_counts_by_company"], {"BGS": 20, "PSA": 2})
        legacy = finding["degraded_samples"]
        self.assertEqual([row["company"] for row in legacy[:4]], ["BGS", "PSA", "BGS", "PSA"])
        self.assertIn("PSA", {row["company"] for row in legacy})
        self.assertLessEqual(len(legacy), 20)
        self.assertEqual(metrics["degraded_grading_sources"], 22)
        self.assertEqual(metrics["grading_companies_with_healthy_source"], 3)

    def test_samples_keep_explicit_context_and_do_not_guess_failure_class(self):
        finding, _findings, _metrics = self._audit()
        bgs = finding["degraded_samples_by_company"]["BGS"][0]
        psa = finding["degraded_samples_by_company"]["PSA"][0]
        self.assertEqual(bgs["failure_class"], "provider_maintenance_redirect")
        self.assertEqual(psa["failure_class"], "unclassified")
        for row in (bgs, psa):
            self.assertTrue(row["company"])
            self.assertTrue(row["source"])
            self.assertTrue(row["market"])
            self.assertTrue(row["kind"])
            self.assertTrue(row["error"])

    def test_existing_severity_and_status_contract_is_unchanged(self):
        finding, findings, _metrics = self._audit()
        self.assertEqual(finding["severity"], "high")
        self.assertFalse(any(row.get("code") == "INVALID_GRADING_SOURCE" for row in findings))


if __name__ == "__main__":
    unittest.main()
