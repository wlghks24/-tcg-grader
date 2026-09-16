import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path

import collection_verification_gate as gate


class ValidGradingSourceCoverageV249Tests(unittest.TestCase):
    def _snapshot(self, now: dt.datetime) -> dict:
        sources = {
            "psa-1": {"company": "PSA", "status": "ok", "url": "https://www.psacard.com/services/tradingcardgrading"},
            "psa-2": {"company": "PSA", "status": "degraded", "url": "https://www.psacard.com/articles", "error": "HTTPError: status 403"},
            "bgs-1": {"company": "BGS", "status": "ok", "url": "https://www.beckett.com/grading"},
            "bgs-2": {"company": "BGS", "status": "degraded", "url": "https://www.beckett.com/news/", "error": "maintenance"},
            "tag-1": {"company": "TAG", "status": "ok", "url": "https://taggrading.com/"},
            "tag-2": {"company": "TAG", "status": "degraded", "url": "https://www.taggrading.com/", "error": "temporary"},
            "brg-1": {"company": "BRG", "status": "ok", "url": "https://break.co.kr/"},
            "brg-2": {"company": "BRG", "status": "degraded", "url": "https://www.break.co.kr/", "error": "temporary"},
            # Both CGC rows use a structurally valid HTTPS URL on an unapproved host.
            # They must not satisfy official-source coverage merely because company='CGC'.
            "cgc-bad-1": {"company": "CGC", "status": "ok", "url": "https://example.com/cgc"},
            "cgc-bad-2": {"company": "CGC", "status": "degraded", "url": "https://example.com/cgc-news", "error": "bad host"},
        }
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

    def test_invalid_rows_do_not_satisfy_official_source_coverage(self):
        now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "grading_company_updates.json").write_text(
                json.dumps(self._snapshot(now), ensure_ascii=False), encoding="utf-8"
            )
            findings = []
            metrics = gate._audit_grading_companies(root, now, findings)

        missing = next(row for row in findings if row.get("code") == "GRADING_COMPANY_WITHOUT_OFFICIAL_SOURCE")
        self.assertEqual(missing["companies"], ["CGC"])
        invalid_targets = {row.get("target") for row in findings if row.get("code") == "INVALID_GRADING_SOURCE"}
        self.assertEqual(invalid_targets, {"cgc-bad-1", "cgc-bad-2"})
        self.assertEqual(metrics["invalid_grading_sources"], 2)
        self.assertEqual(metrics["grading_sources"], 10)

    def test_degraded_but_valid_official_host_still_counts_as_source_coverage(self):
        now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
        snapshot = self._snapshot(now)
        snapshot["sources"]["cgc-bad-1"] = {
            "company": "CGC",
            "status": "degraded",
            "url": "https://www.cgccards.com/news/",
            "error": "temporary upstream failure",
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "grading_company_updates.json").write_text(
                json.dumps(snapshot, ensure_ascii=False), encoding="utf-8"
            )
            findings = []
            gate._audit_grading_companies(root, now, findings)

        missing = [row for row in findings if row.get("code") == "GRADING_COMPANY_WITHOUT_OFFICIAL_SOURCE"]
        self.assertEqual(missing, [])
        invalid_targets = {row.get("target") for row in findings if row.get("code") == "INVALID_GRADING_SOURCE"}
        self.assertEqual(invalid_targets, {"cgc-bad-2"})


if __name__ == "__main__":
    unittest.main()
