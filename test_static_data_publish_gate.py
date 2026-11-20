from __future__ import annotations

import datetime as dt
import shutil
import subprocess
import unittest
from pathlib import Path

import static_data_publish_gate as gate


class StaticDataPublishGateTests(unittest.TestCase):
    def test_expired_event_remains_preserved_but_blocks_active_public_list(self):
        now = dt.datetime(2026, 11, 9, 8, tzinfo=dt.timezone.utc)
        expired = {"name_ko": "지난 행사", "end_date": "2026-10-31",
                   "claim_deadline": "2026-10-31", "lifecycle": "current",
                   "source": "https://example.invalid/secret"}
        promo = {"updated_at": now.isoformat(), "items": [expired], "archive_items": []}
        before = __import__("copy").deepcopy(promo)
        findings = gate.audit_event_lifecycle_snapshot(promo, now=now)
        self.assertIn("ACTIVE_EVENT_ARCHIVE_OVERDUE", {row["code"] for row in findings})
        self.assertEqual([1], findings[-1]["row_indices"])
        self.assertNotIn("example.invalid", str(findings))
        self.assertEqual(before, promo, "read-only audit must never delete event evidence")

    def test_correctly_partitioned_recent_and_movie_tracking_stay_visible(self):
        now = dt.datetime(2026, 11, 9, 8, tzinfo=dt.timezone.utc)
        promo = {"updated_at": now.isoformat(),
                 "items": [
                    {"end_date": "2026-11-07", "claim_deadline": "2026-11-07",
                     "lifecycle": "recently_ended"},
                    {"end_date": "2027-12-31", "claim_deadline": "2027-12-31",
                     "tracking_only": True, "date_precision": "unannounced",
                     "lifecycle": "current"},
                 ], "archive_items": [
                    {"end_date": "2026-10-20", "claim_deadline": "2026-10-20",
                     "lifecycle": "archive"},
                 ]}
        self.assertEqual([], gate.audit_event_lifecycle_snapshot(promo, now=now))

    def test_unannounced_movie_uses_tracking_not_placeholder_expiration(self):
        now = dt.datetime(2026, 11, 10, 8, tzinfo=dt.timezone.utc)
        tracker = {
            "category": "movie", "tracking_only": True,
            "date_precision": "unannounced", "date_label": "공식 개봉일 미발표",
            "start_date": "2025-01-01", "end_date": "2025-01-31",
            "claim_deadline": "2025-01-31", "archive_on": "2025-02-06",
            "lifecycle": "archive",
        }
        events = gate.update_promo_events
        self.assertIsNone(events.effective_expiry(tracker))
        self.assertFalse(events.is_expired(tracker, today=now.date()))
        current, archive = events.partition_event_lifecycle([tracker], today=now.date())
        self.assertEqual([], archive)
        self.assertEqual("current", current[0]["lifecycle"])
        self.assertNotIn("archive_on", current[0])
        self.assertEqual("unannounced", current[0]["date_precision"])
        self.assertEqual("공식 개봉일 미발표", current[0]["date_label"])
        self.assertEqual([], gate.audit_event_lifecycle_snapshot(
            {"updated_at": now.isoformat(), "items": current, "archive_items": []}, now=now))
        # A truly dated film must still archive after the published deadline.
        confirmed = {**tracker, "date_precision": "day", "tracking_only": False}
        self.assertEqual("archive", events.lifecycle_state(confirmed, today=now.date()))
        live, past = events.partition_event_lifecycle([confirmed], today=now.date())
        self.assertEqual([], live)
        self.assertEqual(1, len(past))
        self.assertIn("archive_on", past[0])

    @unittest.skipUnless(shutil.which("node"), "Node.js required for browser lifecycle regression")
    def test_browser_unannounced_movie_never_uses_placeholder_as_expiry(self):
        """Exercise the exact tablet browser function, not a copied Python policy."""
        html = (Path(__file__).resolve().parent / "index.html").read_text(encoding="utf-8")
        source = html[html.index("function promoLifecycle("):html.index("function infoGameKey(")]
        node = r"""
const assert=require('node:assert/strict');
const INFO_ARCHIVE_GRACE_DAYS=5;
const localDateOnly=value=>value?new Date(String(value)+'T00:00:00'):null;
const addLocalDays=(date,days)=>{const d=new Date(date);d.setDate(d.getDate()+days);return d;};
"""
        cases = r"""
const tracking={category:'movie',tracking_only:true,date_precision:'unannounced',
   start_date:'2020-01-01',end_date:'2020-02-01',claim_deadline:'2020-02-01'};
assert.equal(promoLifecycle(tracking),'current');
assert.equal(promoLifecycle({...tracking,date_precision:'day',tracking_only:false}),'archive');
assert.equal(promoLifecycle({...tracking,date_precision:'day'}),'archive');
assert.equal(promoLifecycle({...tracking,tracking_only:false}),'archive');
console.log('movie-lifecycle-ui-pass');
"""
        proc=subprocess.run(["node","-e",node+source+cases],
                            capture_output=True,text=True,check=False,timeout=15)
        self.assertEqual(0,proc.returncode,proc.stderr)
        self.assertIn("movie-lifecycle-ui-pass",proc.stdout)
        self.assertIn('x.tracking_only&&x.date_precision==="unannounced"?escapeDisplayText(',html)
        self.assertIn('"공식 일정 미발표 · 발표 추적 중"',html)

    def test_stale_and_future_event_snapshots_block_publish(self):
        now = dt.datetime(2026, 11, 9, 8, tzinfo=dt.timezone.utc)
        base = {"items": [], "archive_items": []}
        cases = [
            (None, "MISSING_EVENT_SNAPSHOT_TIMESTAMP"),
            ("2026-11-09T05:00:00+00:00", "STALE_EVENT_SNAPSHOT"),
            ("2026-11-09T10:00:00+00:00", "FUTURE_EVENT_SNAPSHOT_TIMESTAMP"),
        ]
        for stamp, code in cases:
            with self.subTest(code=code):
                rows = gate.audit_event_lifecycle_snapshot(
                    {**base, "updated_at": stamp}, now=now, max_age_hours=2)
                self.assertIn(code, {row["code"] for row in rows})

    def test_archive_misplacement_and_stored_state_mismatch_are_rejected(self):
        now = dt.datetime(2026, 11, 9, 8, tzinfo=dt.timezone.utc)
        payload = {"updated_at": now.isoformat(),
                   "items": [{"end_date": "2026-11-30", "lifecycle": "archive"}],
                   "archive_items": [{"end_date": "2026-12-30", "lifecycle": "archive"}]}
        codes = {row["code"] for row in gate.audit_event_lifecycle_snapshot(payload, now=now)}
        self.assertIn("ACTIVE_EVENT_ARCHIVE_OVERDUE", codes)
        self.assertIn("ARCHIVED_EVENT_NOT_EXPIRED", codes)

    def test_real_publish_gate_blocks_unarchived_expired_event(self):
        import tempfile
        import json
        from pathlib import Path
        from unittest import mock
        now = dt.datetime(2026, 11, 9, 8, tzinfo=dt.timezone.utc)
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            payload = {"updated_at": now.isoformat(), "archive_grace_days": 5,
                       "items": [{"end_date": "2026-10-01", "lifecycle": "current"}],
                       "archive_items": []}
            (root / "promo_events.json").write_text(json.dumps(payload), encoding="utf-8")
            with mock.patch.object(gate, "PUBLIC_OUTPUTS", ()), mock.patch.object(gate, "AUX_OUTPUTS", ()):
                result = gate.verify(root, now=now)
        self.assertFalse(result["publish_allowed"])
        self.assertIn("ACTIVE_EVENT_ARCHIVE_OVERDUE",
                      {row["code"] for row in result["findings"]})

    def test_invalid_movie_and_purchase_rows_are_identified_without_leaking_urls(self):
        invalid_movie = {
            "game": "포켓몬 카드", "region": "KR", "name_ko": "잘못된" + chr(10) + "행사",
            "start_date": "2026-10-09", "end_date": "2026-10-08",
            "reward": "확인 중", "condition": "공식 확인 중",
            "source": "http://unverified.example",
        }
        found = gate.first_invalid_public_row(
            "promo_events.json", {"items": [invalid_movie], "archive_items": []})
        self.assertEqual(1, found["invalid_record_index"])
        self.assertNotIn(chr(10), found["invalid_record_name"])
        self.assertNotIn("unverified.example", str(found))
        self.assertEqual({}, gate.first_invalid_public_row(
            "promo_events.json", {"items": [], "archive_items": []}))

        invalid_shop = {
            "name": "CU 공개 매장 안내", "region": "KR", "games": ["Pokemon"],
            "type": "official", "channel": "offline", "chain": "CU",
            "retailer_category": "convenience",
            "official_reference_url": "https://example.org/unverified",
            "url": "https://cu.bgfretail.com/",
        }
        found = gate.first_invalid_public_row(
            "purchase_sources.json", {"sources": [invalid_shop]})
        self.assertEqual(1, found["invalid_record_index"])
        self.assertEqual("CU 공개 매장 안내", found["invalid_record_name"])
        self.assertEqual("ValueError", found["invalid_record_error"])
        self.assertNotIn("example.org", str(found))
        self.assertEqual({}, gate.first_invalid_public_row(
            "purchase_sources.json", {"sources": []}))

    def test_invalid_purchase_snapshot_stays_blocked_with_row_diagnostics(self):
        import tempfile
        import json
        from pathlib import Path
        from unittest import mock
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "purchase_sources.json").write_text(json.dumps({
                "sources": [{
                    "name": "CU official", "region": "KR", "games": ["Pokemon"],
                    "type": "official", "channel": "offline", "chain": "CU",
                    "retailer_category": "convenience",
                    "official_reference_url": "https://example.org/store",
                    "url": "https://cu.bgfretail.com/",
                }]
            }), encoding="utf-8")
            with mock.patch.object(gate, "PUBLIC_OUTPUTS", ("purchase_sources.json",)):
                result = gate.verify(root)
        rows = [row for row in result["findings"]
                if row.get("code") == "INVALID_PUBLIC_OUTPUT"]
        self.assertEqual(1, len(rows))
        self.assertEqual("critical", rows[0]["severity"])
        self.assertEqual(1, rows[0]["invalid_record_index"])
        self.assertFalse(result["publish_allowed"])

    def test_public_outputs_follow_auto_update_contract(self):
        expected = tuple(output_name for _, _, output_name in gate.auto_update_all.JOBS)
        self.assertEqual(expected, gate.PUBLIC_OUTPUTS)
        self.assertEqual(8, len(gate.PUBLIC_OUTPUTS))
        self.assertIn("grading_company_updates.json", gate.PUBLIC_OUTPUTS)

    def test_expected_topic_matrix_matches_shared_collector_contract(self):
        self.assertGreaterEqual(gate.EXPECTED_TOPIC_CELLS, 207)
        self.assertEqual(
            gate.EXPECTED_TOPIC_CELLS,
            len(__import__("update_promo_events").social_topic_expected_keys()),
        )

    def test_expanded_official_games_do_not_become_unattempted_social_cells(self):
        import update_promo_events as promo

        collector = promo.multi_route_event_discovery
        expected_keys = {
            f"{game}/{region}/{topic}"
            for game in collector.GAMES
            for region in collector.REGIONS
            for topic in collector.COVERAGE_TOPICS
        }
        self.assertEqual(set(promo.social_topic_expected_keys()), expected_keys)
        self.assertEqual(gate.EXPECTED_TOPIC_CELLS, len(expected_keys))
        # Promoted titles remain covered by separate official discovery,
        # not imaginary extra jobs in the core social discovery matrix.
        self.assertTrue(set(collector.GAMES).issubset(set(promo.GAMES)))
        for game in set(promo.GAMES) - set(collector.GAMES):
            self.assertFalse(any(key.startswith(f"{game}/") for key in expected_keys))

    def test_zero_discovered_leads_do_not_equal_unattempted_collection(self):
        promo = {
            "social_topic_expected_cells": gate.EXPECTED_TOPIC_CELLS,
            "social_topic_attempted_cells": gate.EXPECTED_TOPIC_CELLS,
            "social_topic_failed_cells": [],
            "social_topic_undiscovered_cells": [f"cell-{i}" for i in range(gate.EXPECTED_TOPIC_CELLS)],
        }
        social = {
            "topic_query_expected_cells": gate.EXPECTED_TOPIC_CELLS,
            "topic_query_attempted_cells": gate.EXPECTED_TOPIC_CELLS,
        }
        findings = gate.audit_topic_contract(promo, social)
        self.assertFalse(any(x["severity"] == "critical" for x in findings))
        self.assertTrue(any(x["code"] == "TOPIC_NO_LEAD_FOUND" for x in findings))

    def test_unattempted_topic_cell_fails_closed(self):
        promo = {
            "social_topic_expected_cells": gate.EXPECTED_TOPIC_CELLS,
            "social_topic_attempted_cells": gate.EXPECTED_TOPIC_CELLS - 1,
        }
        social = {
            "topic_query_expected_cells": gate.EXPECTED_TOPIC_CELLS,
            "topic_query_attempted_cells": gate.EXPECTED_TOPIC_CELLS - 1,
        }
        findings = gate.audit_topic_contract(promo, social)
        codes = {x["code"] for x in findings if x["severity"] == "critical"}
        self.assertIn("TOPIC_COLLECTION_NOT_FULLY_ATTEMPTED", codes)
        self.assertIn("SOCIAL_TOPIC_ATTEMPT_CONTRACT_MISMATCH", codes)

    def test_provider_failure_is_reported_without_relabeling_zero_result_as_gap(self):
        promo = {
            "social_topic_expected_cells": gate.EXPECTED_TOPIC_CELLS,
            "social_topic_attempted_cells": gate.EXPECTED_TOPIC_CELLS,
            "social_topic_failed_cells": ["나루토 카드/US/movie"],
        }
        social = {
            "topic_query_expected_cells": gate.EXPECTED_TOPIC_CELLS,
            "topic_query_attempted_cells": gate.EXPECTED_TOPIC_CELLS,
        }
        findings = gate.audit_topic_contract(promo, social)
        warning = next(x for x in findings if x["code"] == "TOPIC_PROVIDER_FAILURES_PRESERVED")
        self.assertEqual("warning", warning["severity"])
        self.assertEqual(1, warning["count"])


if __name__ == "__main__":
    unittest.main()
