"""Scoped W201/W301 static source proof: no installer or Termux execution."""
from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "execution"))
import version_review_findings as findings

BASE = "6c78831bbb6e188717f86ef90243a836d2e0b67a"
LEDGER = ROOT / "execution/evidence/version_review_findings_v001_v879.json"


def source(path: str) -> str:
    p = subprocess.run(["git", "show", BASE + ":" + path], cwd=ROOT,
                       capture_output=True, text=True, check=True, timeout=20)
    return p.stdout


class SourceBoundaries(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ledger = findings.read_json(LEDGER)
        cls.records = {r["id"]: r for r in cls.ledger["findings"]}

    def test_original_blob_anchors_not_made_up(self):
        for name in ("W201-F001", "W201-F002", "W301-F001"):
            row = self.records[name]
            self.assertIsNone(row["quality_score"])
            self.assertIs(row["physical_tablet_verified"], False)
            self.assertEqual("OPEN_LINEAGE_GUARD", row["state"])
            for item in row["source_refs"]:
                with self.subTest(id=name, path=item["path"]):
                    self.assertEqual(
                        findings.baseline_blob(ROOT, BASE, item["path"]),
                        item["blob"],
                    )

    def test_v273_manifest_target_race_is_a_mock_not_physical_receipt(self):
        text = source("test_tablet_manifest_target_race_v273.py")
        performance = source("tablet_gdrive_sync_perf_v262.py")
        shell = source("ANDROID_UPDATE_AND_START.sh")
        self.assertIn("mock.patch.object(perf.subprocess, \"run\"", text)
        self.assertIn('kwargs["env"]["TCG_TARGET_MAIN_SHA"]', text)
        self.assertIn("def pinned_ensure_exact_main(", performance)
        self.assertIn('env["TCG_TARGET_MAIN_SHA"] = expected_sha', performance)
        self.assertIn('git merge --ff-only "$TARGET_MAIN_SHA"', shell)
        self.assertNotIn("DEVICE_VERIFIED", self.records["W201-F001"]["state"])

    def test_v290_ocr_pinned_bytes_not_equal_successful_install(self):
        script = source("ensure_tesseract_kor.sh")
        tests = source("test_tesseract_kor_supply_chain_v290.py")
        self.assertIn('EXPECTED_BLOB_SHA1="60986d44497689f3abace0b148199476d93292e1"', script)
        self.assertIn('EXPECTED_SIZE="1677415"', script)
        self.assertIn('mv -f -- "$TMP" "$TARGET"', script)
        self.assertIn("def test_download_is_bounded_origin_checked_and_no_follow", tests)
        self.assertEqual("OPEN_LINEAGE_GUARD", self.records["W201-F002"]["state"])

    def test_v376_receipt_explicitly_denies_device_and_drive_proof(self):
        contract = json.loads(source(
            "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V376.json"))
        receipt = json.loads(source(
            "TCG_CROSSCHECK/TCG_GRADER/tablet_gpt_learning_receipt_v376.json"))
        self.assertTrue(contract["candidate_sync"]["requires_exact_watched_path_match"])
        self.assertTrue(contract["rules"]["required_checks_must_succeed_before_merge"])
        self.assertFalse(receipt["verification"]["physical_tablet_runtime_verified"])
        self.assertFalse(receipt["verification"]["physical_drive_readback_verified"])
        self.assertTrue(receipt["verification"]["device_reverification_required"])

    def test_three_new_open_gaps_carry_to_last_window(self):
        head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT,
                              capture_output=True, text=True, check=True).stdout.strip()
        out = findings.validate(self.ledger, ROOT, head=head, latest=879)
        self.assertEqual(13, out["finding_count"])
        windows = out["window_carry_forward"]
        for name in ("W201-F001", "W201-F002"):
            self.assertNotIn(name, windows[1]["open_carry_forward_ids"])
            self.assertIn(name, windows[2]["open_carry_forward_ids"])
            self.assertIn(name, windows[8]["open_carry_forward_ids"])
        self.assertNotIn("W301-F001", windows[2]["open_carry_forward_ids"])
        self.assertIn("W301-F001", windows[3]["open_carry_forward_ids"])
        self.assertIn("W301-F001", windows[8]["open_carry_forward_ids"])
        self.assertIsNone(out["quality_score"])
        self.assertEqual(0, out["complete_version_reviews"])
        self.assertIs(out["release_approval"], False)


if __name__ == "__main__":
    unittest.main()
