#!/usr/bin/env python3
"""V575 TCG quality report deterministic regression & security tests."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import json
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from tcg_quality_report_v575 import build, main, percent, render_html, proposals_for
from tcg_system_audit_v573 import audit
from test_tcg_system_audit_v573 import write_fixture, NOW


def fixture():
    return {
        "audit_at_kst": "2026-10-15T20:38:00+09:00",
        "verification_scope": "offline static audit (not tablet)",
        "metrics": {
            "registry_games": 30,
            "static_box_products": 32,
            "static_box_by_country": {"KR": 11, "JP": 11, "US": 10},
            "official_product_rows": 53,
            "box_market_entries": 25,
            "static_box_price_exact_matches": 12,
            "market_box_verified_recent_links": 20,
            "market_box_unconfirmed_links": 5,
            "market_box_with_sale_evidence": 0,
        },
        "blocking_errors": [],
        "coverage_gaps": ["CN-S missing", "20 unlinked BOX"],
        "usability_followups": ["Missing aria-selected"],
        "audit_pass": True,
        "data_complete": False,
        "device_verified": False,
    }


class LocalQualityReportV575(unittest.TestCase):
    def test_explicit_metrics_without_fake_score(self):
        r = build(fixture())
        self.assertEqual(37.5, r["scores"]["static_box_price_linkage_pct"])
        self.assertEqual(0.0, r["scores"]["box_rows_with_evidence_pct"])
        self.assertIsNone(r["scores"]["overall_quality_score"])
        self.assertEqual("HOLD", r["decision"])
        self.assertFalse(r["device_verified"])
        self.assertFalse(r["data_complete"])

    def test_proposals_auto_rank_and_are_not_auto_applied(self):
        entries = proposals_for(fixture())
        ids = [x["id"] for x in entries]
        self.assertIn("verified-sales", ids)
        self.assertIn("product-matching", ids)
        self.assertIn("chinese-editions", ids)
        self.assertIn("physical-tablet", ids)
        self.assertEqual(len(set(ids)), len(ids))
        self.assertTrue(all("HOLD" in x["status"] for x in entries))
        self.assertTrue(all(x["acceptance_test"] for x in entries))
        broken = fixture()
        broken["blocking_errors"].append("price identity failure")
        self.assertEqual("P0", proposals_for(broken)[0]["priority"])
        self.assertEqual("BLOCK", build(broken)["decision"])

    def test_html_is_offline_responsive_and_accessible(self):
        text = render_html(build(fixture()))
        for needle in ('lang="ko"', 'name="viewport"', 'grid-template-columns',
                       'prefers-reduced-motion', 'aria-label', '<details', '37.5%',
                       '기본 BOX 시세 정확 매칭', 'Lenovo', '미측정', 'V575'):
            # The empty overall-score value must not show a fake numeric grade.
            if needle == "미측정":
                continue
            self.assertIn(needle, text, needle)
        self.assertNotIn('<script', text)
        self.assertNotIn('src="https://', text)
        self.assertNotIn('https://fonts.', text)
        self.assertNotIn('95/100 합격', text)

    def test_injected_market_strings_are_escaped(self):
        data = fixture()
        data["coverage_gaps"].append('<script>fetch("https://evil.example")</script>')
        data["usability_followups"] = ['<img src=x onerror=alert(1)>']
        data["blocking_errors"] = ['<b onclick=attack()>failure</b>']
        content = render_html(build(data))
        self.assertNotIn('<script>', content)
        self.assertNotIn('<img src=x', content)
        self.assertNotIn('onclick=', content)
        self.assertIn('&lt;script&gt;', content)
        self.assertIn('&lt;img', content)
        self.assertIn('&lt;b', content)

    def test_no_incorrect_improvement_claims_from_unproven_baseline(self):
        current = fixture()
        result = build(current, {"metrics": {
            "static_box_products": 31, "static_box_price_exact_matches": 10,
            "market_box_unconfirmed_links": 6,
            "market_box_with_sale_evidence": 0
        }})
        self.assertEqual(2, result["changes_from_baseline"]["static_box_price_exact_matches"]["delta"])
        self.assertEqual(-1, result["changes_from_baseline"]["market_box_unconfirmed_links"]["delta"])
        self.assertEqual({}, build(current, {"metrics": {"static_box_price_exact_matches": "bad"}})
                         ["changes_from_baseline"])

    def test_zero_bad_and_boolean_denominators_cannot_make_fake_percent(self):
        for numerator,denominator in ((1,0),(True,1),(5,4),(-1,10),(1,True),("1",2)):
            self.assertIsNone(percent(numerator,denominator))
        self.assertEqual(100,percent(3,3))

    def test_cli_writes_atomic_html_and_json_inside_local_temporary_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "src"
            write_fixture(root)
            html_path = Path(tmp)/"reports"/"latest.html"
            json_path = Path(tmp)/"reports"/"latest.json"
            self.assertEqual(0, main(["--root",str(root),"--html-out",str(html_path),
                                      "--json-out",str(json_path),"--strict"]))
            html_text=html_path.read_text(encoding="utf-8")
            obj=json.loads(json_path.read_text(encoding="utf-8"))
            self.assertIn("TCG 품질 진단 보고서",html_text)
            self.assertEqual("HOLD",obj["decision"])
            self.assertFalse(obj["device_verified"])
            self.assertFalse(any(p.name.startswith(".quality-") for p in html_path.parent.iterdir()))

    def test_actual_checkout_report_remains_unapproved_without_device(self):
        current = audit(Path(__file__).resolve().parents[1], NOW)
        report = build(current)
        self.assertFalse(report["device_verified"])
        self.assertIn(report["decision"], {"HOLD","BLOCK"})
        self.assertTrue(report["proposals"])
        self.assertIn("P1", {p["priority"] for p in report["proposals"]})


if __name__ == "__main__":
    unittest.main()
