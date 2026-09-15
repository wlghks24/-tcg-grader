#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path

import collection_verification_gate as gate


class CollectionVerificationReportingV243Tests(unittest.TestCase):
    def test_no_healthy_company_finding_excludes_other_company_degraded_samples(self):
        now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
        companies = {name: {} for name in gate.EXPECTED_GRADING_COMPANIES}
        sources = {
            "psa-jp-pricing": {"company": "PSA", "status": "ok", "url": "https://www.psacard.com/ja-JP/services/tradingcardgrading/grading"},
            "psa-us-pricing": {"company": "PSA", "status": "degraded", "url": "https://www.psacard.com/services/tradingcardgrading", "error": "HTTPError: status 403"},
            "bgs-pricing": {"company": "BGS", "status": "degraded", "url": "https://www.beckett.com/grading", "error": "ValueError: unapproved host: beckett-maintenance-page.s3.amazonaws.com"},
            "bgs-news": {"company": "BGS", "status": "degraded", "url": "https://www.beckett.com/news/", "error": "ValueError: unapproved host: beckett-maintenance-page.s3.amazonaws.com"},
            "cgc-pricing": {"company": "CGC", "status": "ok", "url": "https://www.cgccards.com/submit/services-fees/cgc/"},
            "cgc-news": {"company": "CGC", "status": "ok", "url": "https://www.cgccards.com/news/"},
            "tag-pricing": {"company": "TAG", "status": "ok", "url": "https://taggrading.com/collections/grading-services-official"},
            "tag-news": {"company": "TAG", "status": "ok", "url": "https://taggrading.com/blogs/news"},
            "brg-pricing": {"company": "BRG", "status": "ok", "url": "https://break.co.kr/"},
            "brg-news": {"company": "BRG", "status": "ok", "url": "https://break.co.kr/"},
            "psa-jp-news": {"company": "PSA", "status": "ok", "url": "https://www.psacard.com/ja-JP/articles"},
        }
        snapshot = {
            "schema_version": 1,
            "checked_at": now.isoformat(),
            "policy": {
                "official_sources_only": True,
                "community_posts_are_leads_only": True,
                "automatic_source_code_mutation": False,
                "last_good_retained_on_failure": True,
            },
            "companies": companies,
            "sources": sources,
            "recent_changes": [],
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "grading_company_updates.json").write_text(
                json.dumps(snapshot, ensure_ascii=False), encoding="utf-8"
            )
            findings: list[dict] = []
            metrics = gate._audit_grading_companies(root, now, findings)

        target = next(row for row in findings if row.get("code") == "GRADING_COMPANY_NO_HEALTHY_SOURCE")
        self.assertEqual(target.get("companies"), ["BGS"])
        self.assertEqual({row.get("source") for row in target.get("degraded_samples", [])}, {"bgs-pricing", "bgs-news"})
        self.assertNotIn("psa-us-pricing", {row.get("source") for row in target.get("degraded_samples", [])})
        self.assertEqual(metrics.get("degraded_grading_sources"), 3)
        self.assertEqual(metrics.get("grading_companies_with_healthy_source"), 4)


if __name__ == "__main__":
    unittest.main()
