"""V653 receipts are bounded, idempotent, and never neural-training evidence."""
import json
import tempfile
import unittest
from io import StringIO
from contextlib import redirect_stdout
from unittest.mock import patch
from datetime import datetime, timedelta, timezone
from pathlib import Path
from execution.tablet_autonomy_collection_receipts_v653 import (
    NAME, Hold, capture, observe, preflight, main as receipt_main,
)

NOW = datetime(2026, 10, 19, 11, 0, tzinfo=timezone.utc)

class ReceiptTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "root"
        self.state = Path(self.tmp.name) / "state"
        self.root.mkdir()
        self.state.mkdir()
        self.make(NOW - timedelta(minutes=15))

    def make(self, end, *, ok=True, degraded=0):
        start = end - timedelta(minutes=10)
        jobs = []
        for name in ("market_prices.json", "market_watch.json"):
            obj = {"updated_at": end.isoformat(), "collection_errors": [], "collection_status": "정상",
                   **({"entries": {"sample": {"price": 1}}} if name == "market_prices.json" else {"items": []})}
            (self.root / name).write_text(json.dumps(obj))
            jobs.append({"file": name, "ok": ok, "updated_at": end.isoformat(),
                         "collection_errors": [], "remaining_collection_errors": []})
        report = {"started_at": start.isoformat(), "finished_at": end.isoformat(),
                  "trigger": "automatic-final", "ok": ok,
                  "failure_count": 0 if ok else 1, "degraded_count": degraded,
                  "fresh_failure_count": 0, "results": jobs,
                  "postflight_monitor": {"ok": True, "results": [{"file": j["file"], "ok": True} for j in jobs]}}
        (self.root / "auto_update_report.json").write_text(json.dumps(report))

    def test_genuine_first_and_second_observation(self):
        x = capture(self.root, self.state, now=NOW)
        self.assertEqual("OBSERVATION_RECORDED_NOT_VERIFIED", x["status"])
        self.assertEqual(1, x["count"])
        self.make(NOW-timedelta(minutes=1))
        y = capture(self.root, self.state, now=NOW)
        self.assertEqual(2, y["count"])
        obs = json.loads((self.state / NAME).read_text())["observations"]
        self.assertTrue(all(not r["verified_neural_outcome"] for r in obs))
        self.assertFalse((self.root / "tablet_autonomy_verified_outcomes.jsonl").exists())

    def test_six_jobs_seven_postflight_rows_check_two_required_files(self):
        """Different counts are not a failure if both required outputs match."""
        path = self.root / "auto_update_report.json"
        value = json.loads(path.read_text())
        for i in range(4):
            value["results"].append({
                "file": f"additional-{i}.json",
                "ok": True, "updated_at": value["finished_at"],
                "collection_errors": [], "remaining_collection_errors": [],
            })
        for i in range(5):
            value["postflight_monitor"]["results"].append({
                "file": f"additional-postflight-{i}.json", "ok": True,
            })
        path.write_text(json.dumps(value))
        self.assertEqual(6, len(value["results"]))
        self.assertEqual(7, len(value["postflight_monitor"]["results"]))
        before = {x.name: x.read_bytes() for x in self.root.iterdir()}
        result = preflight(self.root, now=NOW)
        self.assertEqual("OBSERVATION_ELIGIBLE_NOT_VERIFIED", result["status"])
        self.assertFalse(result["training_enabled"])
        self.assertFalse(result["writes"])
        self.assertEqual(before, {x.name: x.read_bytes() for x in self.root.iterdir()})
        self.assertFalse((self.root / "tablet_autonomy_verified_outcomes.jsonl").exists())

    def test_seven_postflight_rows_missing_required_market_is_hold(self):
        path = self.root / "auto_update_report.json"
        value = json.loads(path.read_text())
        value["postflight_monitor"]["results"] = [
            {"file": "market_watch.json", "ok": True},
            *[{"file": f"extra-{i}.json", "ok": True} for i in range(6)],
        ]
        path.write_text(json.dumps(value))
        result = preflight(self.root, now=NOW)
        self.assertEqual("EVIDENCE_HOLD", result["status"])
        self.assertIn("market_prices.json", result["reason"])

    def test_six_jobs_with_failed_required_market_is_hold(self):
        path = self.root / "auto_update_report.json"
        value = json.loads(path.read_text())
        value["results"][0]["ok"] = False
        for i in range(4):
            value["results"].append({
                "file": f"extra-{i}.json",
                "ok": True, "updated_at": value["finished_at"],
            })
        path.write_text(json.dumps(value))
        result = preflight(self.root, now=NOW)
        self.assertEqual("EVIDENCE_HOLD", result["status"])
        self.assertIn("JOB_FAILED_market_prices.json", result["reason"])

    def test_check_only_requires_no_state_dir_and_returns_safe_status(self):
        result = preflight(self.root, now=NOW)
        self.assertEqual("OBSERVATION_ELIGIBLE_NOT_VERIFIED", result["status"])
        self.assertTrue(result["read_only"])
        self.assertFalse(result["verified_neural_outcome"])
        self.assertFalse(result["training_enabled"])

    def test_idempotent_report(self):
        capture(self.root, self.state, now=NOW)
        self.assertEqual("ALREADY_OBSERVED", capture(self.root, self.state, now=NOW)["status"])

    def test_old_report_is_hold(self):
        self.make(NOW - timedelta(days=4))
        self.assertEqual("EVIDENCE_HOLD", capture(self.root, self.state, now=NOW)["status"])

    def test_failed_job_is_hold(self):
        self.make(NOW - timedelta(minutes=1), ok=False)
        self.assertEqual("EVIDENCE_HOLD", capture(self.root, self.state, now=NOW)["status"])

    def test_degraded_job_is_hold(self):
        self.make(NOW - timedelta(minutes=1), degraded=1)
        self.assertEqual("EVIDENCE_HOLD", capture(self.root, self.state, now=NOW)["status"])

    def test_mismatched_market_output_is_hold(self):
        p = self.root / "market_prices.json"
        d = json.loads(p.read_text())
        d["updated_at"] = (NOW-timedelta(days=1)).isoformat()
        p.write_text(json.dumps(d))
        self.assertEqual("EVIDENCE_HOLD", capture(self.root, self.state, now=NOW)["status"])

    def test_missing_postflight_is_hold(self):
        p = self.root / "auto_update_report.json"
        report = json.loads(p.read_text())
        report.pop("postflight_monitor")
        p.write_text(json.dumps(report))
        self.assertEqual("POSTFLIGHT_NOT_VERIFIED", capture(self.root, self.state, now=NOW)["reason"])

    def test_postflight_file_failed_is_hold(self):
        p = self.root / "auto_update_report.json"
        report = json.loads(p.read_text())
        report["postflight_monitor"]["results"][0]["ok"] = False
        p.write_text(json.dumps(report))
        self.assertEqual("POSTFLIGHT_FILE_NOT_VERIFIED_market_prices.json",
                         capture(self.root, self.state, now=NOW)["reason"])

    def test_output_source_errors_is_hold_even_if_report_says_ok(self):
        p = self.root / "market_prices.json"
        report = json.loads(p.read_text())
        report["collection_errors"] = ["HTTP 403"]
        p.write_text(json.dumps(report))
        self.assertEqual("OUTPUT_SOURCE_ERRORS_market_prices.json",
                         capture(self.root, self.state, now=NOW)["reason"])

    def test_output_health_mismatch_is_hold(self):
        p = self.root / "market_watch.json"
        report = json.loads(p.read_text())
        report["collection_status"] = "degraded"
        p.write_text(json.dumps(report))
        self.assertEqual("OUTPUT_NOT_HEALTHY_market_watch.json",
                         capture(self.root, self.state, now=NOW)["reason"])

    def test_symlinked_report_is_hold(self):
        p = self.root / "auto_update_report.json"
        p.rename(self.root / "saved")
        p.symlink_to(self.root / "saved")
        self.assertEqual("EVIDENCE_HOLD", capture(self.root, self.state, now=NOW)["status"])

    def test_state_corruption_is_not_overwritten(self):
        p = self.state / NAME
        p.write_text("corrupt-state")
        res = capture(self.root, self.state, now=NOW)
        self.assertEqual("EVIDENCE_HOLD", res["status"])
        self.assertEqual("corrupt-state", p.read_text())

    def test_forged_observation_promotion_is_held_without_overwrite(self):
        for field, forged in (
            ("training_enabled", True),
            ("external_source_truth_verified", True),
            ("verified_neural_outcome", True),
            ("observation_only", False),
        ):
            with self.subTest(field=field):
                (self.state / NAME).unlink(missing_ok=True)
                self.make(NOW - timedelta(minutes=15))
                self.assertTrue(capture(self.root, self.state, now=NOW)["written"])
                p = self.state / NAME
                saved = json.loads(p.read_text())
                saved["observations"][0][field] = forged
                p.write_text(json.dumps(saved), encoding="utf-8")
                before = p.read_bytes()
                self.make(NOW - timedelta(minutes=1))
                result = capture(self.root, self.state, now=NOW)
                self.assertEqual("EVIDENCE_HOLD", result["status"])
                self.assertEqual("UNTRUSTED_STORED_RECEIPT", result["reason"])
                self.assertEqual(before, p.read_bytes())
                self.assertFalse((self.root / "tablet_autonomy_verified_outcomes.jsonl").exists())

    def test_duplicate_stored_receipt_is_held_without_overwrite(self):
        self.assertTrue(capture(self.root, self.state, now=NOW)["written"])
        p = self.state / NAME
        saved = json.loads(p.read_text())
        saved["observations"].append(dict(saved["observations"][0]))
        p.write_text(json.dumps(saved), encoding="utf-8")
        before = p.read_bytes()
        self.make(NOW - timedelta(minutes=1))
        result = capture(self.root, self.state, now=NOW)
        self.assertEqual("REPLAY_OR_TIME_REVERSAL", result["reason"])
        self.assertEqual(before, p.read_bytes())

    def test_symlink_state_is_hold(self):
        (self.state / NAME).symlink_to(self.root / "market_prices.json")
        self.assertEqual("STATE_SYMLINK", capture(self.root, self.state, now=NOW)["reason"])

    def test_missing_state_dir_never_created(self):
        p = Path(self.tmp.name) / "missing"
        self.assertEqual("UNSAFE_STATE_DIR", capture(self.root, p, now=NOW)["reason"])
        self.assertFalse(p.exists())

    def test_duplicate_json_keys_is_hold(self):
        (self.root/"auto_update_report.json").write_text('{"ok":true,"ok":true}')
        with self.assertRaises(Hold):
            observe(self.root, now=NOW)

    def test_receipt_cannot_train_meta_neural_model(self):
        value = observe(self.root, now=NOW)
        self.assertFalse(value["training_enabled"])
        self.assertFalse(value["external_source_truth_verified"])
        self.assertFalse(value["verified_neural_outcome"])

    def test_capture_cli_reports_evidence_hold_with_nonzero_exit(self):
        args = ["v653", "--root", str(self.root), "--state-dir", str(self.state)]
        output = StringIO()
        with patch("sys.argv", args), patch(
            "execution.tablet_autonomy_collection_receipts_v653.capture",
            return_value={"status": "EVIDENCE_HOLD", "reason": "BAD_OUTPUT", "written": False}
        ), redirect_stdout(output):
            rc = receipt_main()
        self.assertEqual(3, rc)
        self.assertIn('"EVIDENCE_HOLD"', output.getvalue())
        self.assertIn('"BAD_OUTPUT"', output.getvalue())

    def test_capture_cli_observation_success_is_not_model_evidence(self):
        args = ["v653", "--root", str(self.root), "--state-dir", str(self.state)]
        for status in ("OBSERVATION_RECORDED_NOT_VERIFIED", "ALREADY_OBSERVED"):
            with self.subTest(status=status):
                with patch("sys.argv", args), patch(
                    "execution.tablet_autonomy_collection_receipts_v653.capture",
                    return_value={"status": status, "written": False,
                                  "v387_confidence_unchanged": True}
                ), redirect_stdout(StringIO()) as output:
                    rc = receipt_main()
                self.assertEqual(0, rc)
                self.assertNotIn("verified_neural_outcome", output.getvalue())

    def test_capture_cli_unknown_status_fails_closed(self):
        args = ["v653", "--root", str(self.root), "--state-dir", str(self.state)]
        with patch("sys.argv", args), patch(
            "execution.tablet_autonomy_collection_receipts_v653.capture",
            return_value={"status": "UNKNOWN_BUG", "written": False}
        ), redirect_stdout(StringIO()):
            self.assertEqual(3, receipt_main())

    def test_existing_schedule_only(self):
        sched = (Path(__file__).resolve().parents[1] / "TABLET_SCHEDULED_UPDATE.sh").read_text()
        self.assertIn('SCHEDULE_HOUR="23"', sched)
        self.assertIn('SCHEDULE_MINUTE="00"', sched)
        self.assertIn("execution.tablet_autonomy_collection_receipts_v653", sched)

if __name__ == "__main__":
    unittest.main()
