#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TARGET = ROOT / "collection_verification_gate.py"
TEST = ROOT / "test_grading_diagnostics_v248.py"

old_sample = '''        else:\n            degraded += 1\n            sample = {"source": str(source_id), "error": str(row.get("error") or row.get("last_error") or "")[:300]}\n            if len(degraded_errors) < 20:\n                degraded_errors.append(sample)\n            company_samples = degraded_errors_by_company.setdefault(company, [])\n            if len(company_samples) < 20:\n                company_samples.append(sample)\n'''
new_sample = '''        else:\n            degraded += 1\n            error_text = str(row.get("error") or row.get("last_error") or "")[:300]\n            sample = {\n                "company": company,\n                "source": str(source_id)[:160],\n                "market": str(row.get("market") or "")[:40],\n                "kind": str(row.get("kind") or "")[:40],\n                "failure_class": str(row.get("failure_class") or "unclassified")[:80],\n                "error": error_text,\n            }\n            if len(degraded_errors) < 20:\n                degraded_errors.append(sample)\n            company_samples = degraded_errors_by_company.setdefault(company, [])\n            if len(company_samples) < 20:\n                company_samples.append(sample)\n'''

old_finding = '''    no_healthy = EXPECTED_GRADING_COMPANIES - healthy_companies\n    if no_healthy:\n        no_healthy_samples: list[dict[str, str]] = []\n        for company in sorted(no_healthy):\n            no_healthy_samples.extend(degraded_errors_by_company.get(company, []))\n        findings.append({"severity": "high", "code": "GRADING_COMPANY_NO_HEALTHY_SOURCE", "target": path.name,\n                         "companies": sorted(no_healthy), "degraded_samples": no_healthy_samples[:20]})\n'''
new_finding = '''    no_healthy = EXPECTED_GRADING_COMPANIES - healthy_companies\n    if no_healthy:\n        ordered_companies = sorted(no_healthy)\n        samples_by_company = {\n            company: degraded_errors_by_company.get(company, [])[:5]\n            for company in ordered_companies\n        }\n        no_healthy_samples: list[dict[str, str]] = []\n        for index in range(5):\n            for company in ordered_companies:\n                company_samples = samples_by_company[company]\n                if index < len(company_samples):\n                    no_healthy_samples.append(company_samples[index])\n        findings.append({\n            "severity": "high",\n            "code": "GRADING_COMPANY_NO_HEALTHY_SOURCE",\n            "target": path.name,\n            "companies": ordered_companies,\n            "degraded_samples": no_healthy_samples[:20],\n            "degraded_samples_by_company": samples_by_company,\n        })\n'''

text = TARGET.read_text(encoding="utf-8")
if text.count(old_sample) != 1:
    raise SystemExit("sample anchor mismatch")
if text.count(old_finding) != 1:
    raise SystemExit("finding anchor mismatch")
text = text.replace(old_sample, new_sample).replace(old_finding, new_finding)
TARGET.write_text(text, encoding="utf-8")

TEST.write_text(r'''import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path

import collection_verification_gate as gate


class GradingDiagnosticsV248Tests(unittest.TestCase):
    def _snapshot(self, now: dt.datetime) -> dict:
        sources = {}
        for idx in range(8):
            sources[f"bgs-degraded-{idx}"] = {
                "company": "BGS",
                "status": "degraded",
                "market": "US",
                "kind": "pricing" if idx % 2 == 0 else "news",
                "url": "https://www.beckett.com/grading",
                "failure_class": "provider_maintenance_redirect",
                "last_error": f"maintenance-{idx}",
            }
            sources[f"psa-degraded-{idx}"] = {
                "company": "PSA",
                "status": "degraded",
                "market": "US" if idx % 2 == 0 else "JP",
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

    def test_no_healthy_samples_are_balanced_and_grouped_by_company(self):
        now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "grading_company_updates.json").write_text(
                json.dumps(self._snapshot(now), ensure_ascii=False), encoding="utf-8"
            )
            findings = []
            metrics = gate._audit_grading_companies(root, now, findings)

        finding = next(row for row in findings if row.get("code") == "GRADING_COMPANY_NO_HEALTHY_SOURCE")
        self.assertEqual(finding["companies"], ["BGS", "PSA"])
        grouped = finding["degraded_samples_by_company"]
        self.assertEqual(set(grouped), {"BGS", "PSA"})
        self.assertEqual(len(grouped["BGS"]), 5)
        self.assertEqual(len(grouped["PSA"]), 5)
        legacy = finding["degraded_samples"]
        self.assertEqual(len(legacy), 10)
        self.assertEqual([row["company"] for row in legacy[:4]], ["BGS", "PSA", "BGS", "PSA"])
        self.assertEqual({row["company"] for row in legacy}, {"BGS", "PSA"})
        self.assertEqual(metrics["degraded_grading_sources"], 16)
        self.assertEqual(metrics["grading_companies_with_healthy_source"], 3)

    def test_samples_expose_context_without_inventing_failure_class(self):
        now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "grading_company_updates.json").write_text(
                json.dumps(self._snapshot(now), ensure_ascii=False), encoding="utf-8"
            )
            findings = []
            gate._audit_grading_companies(root, now, findings)
        finding = next(row for row in findings if row.get("code") == "GRADING_COMPANY_NO_HEALTHY_SOURCE")
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
        now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "grading_company_updates.json").write_text(
                json.dumps(self._snapshot(now), ensure_ascii=False), encoding="utf-8"
            )
            findings = []
            gate._audit_grading_companies(root, now, findings)
        finding = next(row for row in findings if row.get("code") == "GRADING_COMPANY_NO_HEALTHY_SOURCE")
        self.assertEqual(finding["severity"], "high")
        self.assertFalse(any(row.get("code") == "INVALID_GRADING_SOURCE" for row in findings))


if __name__ == "__main__":
    unittest.main()
''', encoding="utf-8")
print("patched collection_verification_gate.py and wrote test_grading_diagnostics_v248.py")
