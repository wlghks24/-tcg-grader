"""V1010 read-only Lenovo/Termux delivery readback regression tests."""
from __future__ import annotations

from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
import json
import unittest
from unittest.mock import patch

import execution.tablet_delivery_readback_v1010 as v1010

A = "a" * 40
B = "b" * 40


def valid_report() -> dict:
    return {
        "environment": {"termux": True},
        "git": {"sha_full": A, "branch": "main"},
        "health": {"ok": True},
        "runtime_contract_ok": True,
        "delivery": {
            "code_update_status": "LOCAL_MAIN_CHECK_VERIFIED",
            "code_update_checked_fresh": True,
            "official_origin_verified": True,
            "disk_sha": A,
            "recorded_remote_sha": A,
            "local_origin_main_sha": A,
            "running_sha": A,
            "runtime_status": "RUNNING_SHA_VERIFIED_LOCAL_HTTP",
            "scheduler_status": "LOOP_RUNNING_LOCALLY",
            "boot_script_present": True,
            "ready_for_device_readback": True,
            "physical_tablet_verified": True,
            "reboot_verified": True,
        },
    }


class TabletDeliveryReadbackV1010Tests(unittest.TestCase):
    def test_best_local_evidence_is_not_physical_confirmation(self):
        row = v1010.summarize(valid_report())
        self.assertEqual("READY_FOR_PHYSICAL_CHECK", row["status"])
        self.assertTrue(row["ready_for_physical_check"])
        for flag in ("physical_tablet_verified", "pwa_visual_verified", "reboot_verified",
                     "live_github_main_verified", "device_restart_authorized",
                     "writes_or_updates_performed"):
            self.assertFalse(row[flag])

    def test_termux_absent_must_hold(self):
        report = valid_report()
        report["environment"]["termux"] = False
        row = v1010.summarize(report)
        self.assertEqual("READBACK_HOLD", row["status"])
        self.assertIn("termux_environment_not_observed", row["missing_evidence"])

    def test_old_server_is_actionable_without_auto_restarting(self):
        report = valid_report()
        report["delivery"].update(running_sha=B, runtime_status="RUNNING_SHA_MISMATCH")
        row = v1010.summarize(report)
        self.assertEqual("OLD_SERVER_RUNNING", row["status"])
        self.assertFalse(row["ready_for_physical_check"])
        self.assertEqual(B, row["running_sha"])

    def test_update_failed_hold(self):
        report = valid_report()
        report["delivery"]["code_update_status"] = "MAIN_UPDATE_HOLD"
        self.assertEqual("UPDATE_HOLD", v1010.summarize(report)["status"])

    def test_forged_receipt_or_main_ref_never_passes(self):
        checks = (("code_update_checked_fresh", False), ("official_origin_verified", False),
                  ("recorded_remote_sha", B), ("local_origin_main_sha", B),
                  ("disk_sha", B), ("ready_for_device_readback", False))
        for key, value in checks:
            with self.subTest(key=key):
                report = valid_report()
                report["delivery"][key] = value
                self.assertFalse(v1010.summarize(report)["ready_for_physical_check"])
        report = valid_report()
        report["git"]["branch"] = "feature"
        self.assertFalse(v1010.summarize(report)["ready_for_physical_check"])

    def test_scheduler_boot_and_runtime_are_independent(self):
        for key, value in (("scheduler_status", "LOOP_NOT_VERIFIED"),
                           ("boot_script_present", False),
                           ("runtime_status", "RUNNING_SHA_UNVERIFIED")):
            with self.subTest(key=key):
                report = valid_report()
                report["delivery"][key] = value
                self.assertFalse(v1010.summarize(report)["ready_for_physical_check"])

    def test_fake_health_or_runtime_contract_cannot_claim_running(self):
        report = valid_report()
        report["health"]["ok"] = "true"
        self.assertFalse(v1010.summarize(report)["ready_for_physical_check"])
        report = valid_report()
        report["runtime_contract_ok"] = False
        self.assertFalse(v1010.summarize(report)["ready_for_physical_check"])

    def test_invalid_sha_and_untrusted_statuses_fail_closed(self):
        for bad in ("short", "A" * 39, "$"+"{FAKE}", "a" * 39 + "g", None, 123):
            with self.subTest(bad=bad):
                report = valid_report()
                report["delivery"]["running_sha"] = bad
                row = v1010.summarize(report)
                self.assertEqual("unknown", row["running_sha"])
                self.assertFalse(row["ready_for_physical_check"])
        report = valid_report()
        report["delivery"]["runtime_status"] = "SUCCESS_ALL"
        self.assertEqual("RUNNING_SHA_UNVERIFIED", v1010.summarize(report)["runtime_status"])

    def test_missing_or_bad_json_types_hold(self):
        for item in (None, "", [], {}, {"delivery": None},
                     {"delivery": {"status": "OK"}}):
            with self.subTest(item=item):
                row = v1010.summarize(item)
                self.assertEqual("READBACK_HOLD", row["status"])
                self.assertFalse(row["ready_for_physical_check"])

    def test_korean_summary_is_clear_about_unverified_device(self):
        text = v1010.render_korean(v1010.summarize(valid_report()))
        for part in ("현재 실행 서버:", "태블릿 화면·재부팅 검증: 미완료",
                     "실시간 확인: 수행 안 함", "상태:", "23시 예약·부팅:"):
            self.assertIn(part, text)
        self.assertNotIn("설치 완료", text)

    def test_json_only_uses_local_health_and_no_lan_probe(self):
        with patch.object(v1010.probe, "build_report", return_value=valid_report()) as spy:
            out = StringIO()
            with redirect_stdout(out):
                self.assertEqual(0, v1010.main(["--json"]))
        spy.assert_called_once()
        self.assertFalse(spy.call_args.kwargs["probe_network"])
        self.assertTrue(spy.call_args.kwargs["probe_health"])
        self.assertFalse(json.loads(out.getvalue())["physical_tablet_verified"])

    def test_strict_exit_code_requires_readback_ready(self):
        report = valid_report()
        report["delivery"]["runtime_status"] = "RUNNING_SHA_UNVERIFIED"
        with patch.object(v1010.probe, "build_report", return_value=report):
            with redirect_stdout(StringIO()):
                self.assertEqual(2, v1010.main(["--require-ready"]))
        with patch.object(v1010.probe, "build_report", return_value=valid_report()):
            with redirect_stdout(StringIO()):
                self.assertEqual(0, v1010.main(["--require-ready"]))

    def test_probe_exception_reports_hold_without_secret(self):
        with patch.object(v1010.probe, "build_report", side_effect=OSError("private token")):
            out = StringIO()
            with redirect_stdout(out):
                self.assertEqual(2, v1010.main(["--json", "--require-ready"]))
        self.assertIn('"status": "READBACK_HOLD"', out.getvalue())
        self.assertNotIn("private token", out.getvalue())

    def test_additive_main_entrypoint_never_auto_installs(self):
        root = Path(__file__).resolve().parents[2]
        entry = (root / "main").read_text(encoding="utf-8")
        self.assertIn("delivery-status|device-status)", entry)
        self.assertIn("exec python -m execution.tablet_delivery_readback_v1010", entry)
        self.assertIn("bash main delivery-status", entry)
        self.assertNotIn("tablet_delivery_readback_v1010 && bash TABLET_SCHEDULED_UPDATE.sh run", entry)


if __name__ == "__main__":
    unittest.main(verbosity=2)
