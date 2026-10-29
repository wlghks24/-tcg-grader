"""Unit + real local Git regression tests for the desktop-only auditor."""
from __future__ import annotations
import hashlib
import json
import subprocess
import tempfile
import threading
import unittest
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pc_auditor"))
import audit


def cmd(repo, *args):
    r = subprocess.run(["git", *args], cwd=repo, capture_output=True, check=True)
    return r.stdout.decode().strip()


class AuditorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="tcg-pc-test-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.repo = self.root / "source"
        self.repo.mkdir()
        cmd(self.repo, "init", "-q")
        cmd(self.repo, "config", "user.email", "fixture@example.invalid")
        cmd(self.repo, "config", "user.name", "Fixture")
        (self.repo / "V001_core.py").write_text(
            "import json\ndef check(x):\n    return json.dumps(x)\n", encoding="utf-8")
        (self.repo / "V101_bad.py").write_text("def broken(:\n", encoding="utf-8")
        (self.repo / "V040_grade.py").write_text(
            "def verify(data):\n    return bool(data.get('verified'))\n", encoding="utf-8")
        folder = self.repo / "execution" / "evidence"
        folder.mkdir(parents=True)
        ledger = {"findings": [{"id": "W001-F001", "first_observed_version": 1,
                                 "severity": "P0", "state": "OPEN_SUCCESSOR_REQUIRED",
                                 "summary": "Still open"}]}
        (folder / "version_review_findings_v001_v205.json").write_text(
            json.dumps(ledger), encoding="utf-8")
        cmd(self.repo, "add", ".")
        cmd(self.repo, "commit", "-qm", "V1 source and V101 historical notes")
        self.out = self.root / "output"

    def test_runs_three_windows_with_gap_tracking_and_static_parse_only(self):
        r = audit.run_audit(self.repo, self.out, 205)
        self.assertTrue(r["complete"])
        self.assertEqual(3, len(r["windows"]))
        self.assertEqual([100, 100, 5],
                         [w["hint_slots"] + w["no_hint_slots"] for w in r["windows"]])
        self.assertEqual(3, r["completed_windows"])
        self.assertEqual([1, 1, 1], [w["open_findings"] for w in r["windows"]])
        self.assertFalse(r["physical_tablet_verified"])
        self.assertIsNone(r["quality_score"])
        self.assertEqual(1, r["syntax_issue_count"])
        target = next(self.out.iterdir())
        self.assertIn("NOT_PERFORMED", (target/"V0001_V0100.json").read_text())
        self.assertIn("실기기", (target/"summary.md").read_text())
        data = json.loads((target/"code_map.json").read_text())
        self.assertTrue(any(f["path"] == "V001_core.py" and
                            f["functions"][0]["name"] == "check" for f in data["files"]))
        self.assertEqual(["V101_bad.py"], [x["path"] for x in data["syntax_or_encoding_issues"]])
        self.assertTrue(any(h["rule"] == "TRUTHY_VERIFICATION_FLAG_REVIEW" and
                            h["path"] == "V040_grade.py" for h in data["risk_hints"]))
        self.assertGreaterEqual(r["risk_hint_count"], 1)

    def test_resume_after_one_batch_and_verify_parent_hash(self):
        first = audit.run_audit(self.repo, self.out, 205, stop_after=1)
        self.assertFalse(first["complete"])
        self.assertEqual(1, first["completed_windows"])
        result = audit.run_audit(self.repo, self.out, 205, resume=True)
        self.assertTrue(result["complete"])
        output = next(self.out.iterdir())
        row1 = audit.read_checkpoint(output / "V0001_V0100.json")
        row2 = audit.read_checkpoint(output / "V0101_V0200.json")
        self.assertEqual(row1["checkpoint_sha256"], row2["checkpoint_parent_sha256"])
        with self.assertRaisesRegex(audit.AuditError, "report_folder_exists"):
            audit.run_audit(self.repo, self.out, 205)

    def test_modified_checkpoint_does_not_silently_resume(self):
        audit.run_audit(self.repo, self.out, 205, stop_after=1)
        target = next(self.out.iterdir()) / "V0001_V0100.json"
        data = json.loads(target.read_text())
        data["slots"][0]["status"] = "VERIFIED_BY_AI"  # forged evidence
        target.write_text(json.dumps(data))
        with self.assertRaisesRegex(audit.AuditError, "checkpoint_chain_or_digest_mismatch"):
            audit.run_audit(self.repo, self.out, 205, resume=True)

    def test_change_head_requires_new_checkpoint_folder(self):
        audit.run_audit(self.repo, self.out, 205, stop_after=1)
        (self.repo / "V205_new.py").write_text("x = 2\n")
        cmd(self.repo, "add", ".")
        cmd(self.repo, "commit", "-qm", "V205 update")
        new = audit.run_audit(self.repo, self.out, 205, resume=False, stop_after=1)
        self.assertEqual(1, new["completed_windows"])
        self.assertEqual(2, len(list(self.out.iterdir())))

    def test_reject_report_in_source_and_missing_project(self):
        with self.assertRaisesRegex(audit.AuditError, "output_must_be_outside"):
            audit.run_audit(self.repo, self.repo/"reports", 205)
        with self.assertRaisesRegex(audit.AuditError, "choose_git_checkout_root"):
            audit.run_audit(self.repo/"execution", self.out, 205)

    def test_implicit_max_from_documented_ledger_not_actual_release(self):
        r = audit.run_audit(self.repo, self.out)
        self.assertEqual(205, r["latest"])
        self.assertFalse(r["source_review_complete"])
        self.assertEqual("NOT_RUN_BY_PC_TOOL", r["CI"])

    def test_mid_run_stop_retains_completed_checkpoints(self):
        event = threading.Event()
        def callback(msg):
            if "V1~V100" in msg:
                event.set()
        r = audit.run_audit(self.repo, self.out, 205, callback=callback, stop_event=event)
        self.assertEqual(1, r["completed_windows"])
        self.assertFalse(r["complete"])
        final = audit.run_audit(self.repo, self.out, 205, resume=True)
        self.assertTrue(final["complete"])

    def test_checkpoint_symlink_and_size_limits_fail_closed(self):
        self.out.mkdir()
        destination = self.root / "other.json"
        destination.write_text(json.dumps({"schema": "forged"}))
        link = self.out / "linked.json"
        try:
            link.symlink_to(destination)
        except (NotImplementedError, OSError):
            pass  # Some Windows developer policies disable symlink creation.
        else:
            with self.assertRaisesRegex(audit.AuditError, "unsafe_checkpoint"):
                audit.read_checkpoint(link)
        long_file = self.out / "big.json"
        long_file.write_text(json.dumps({"content": "a" * 2_100_000}))
        with self.assertRaisesRegex(audit.AuditError, "unsafe_checkpoint"):
            audit.read_checkpoint(long_file)
        self.assertEqual("a" * 2_100_000,
                         audit.read_checkpoint(long_file, max_bytes=4_000_000)["content"])

    def test_cli_runs_and_resumes_without_repo_changes(self):
        script = Path(audit.__file__)
        original_head = cmd(self.repo, "rev-parse", "HEAD")
        completed = subprocess.run(
            [sys.executable, str(script), "--repo", str(self.repo),
             "--latest", "205", "--output", str(self.out), "--stop-after", "1"],
            capture_output=True, text=True)
        self.assertEqual(2, completed.returncode, completed.stderr)
        self.assertIn("next 100 blocked", completed.stdout)
        resumed = subprocess.run(
            [sys.executable, str(script), "--repo", str(self.repo),
             "--latest", "205", "--output", str(self.out), "--resume"],
            capture_output=True, text=True)
        self.assertEqual(2, resumed.returncode, resumed.stderr)
        self.assertIn("next 100 blocked", resumed.stdout)
        report = next((self.out/"first_pass").iterdir())
        other = next((self.out/"second_pass").iterdir())
        self.assertTrue((report/"V0001_V0100.json").is_file())
        self.assertTrue((other/"V0001_V0100.json").is_file())
        self.assertFalse((report/"V0101_V0200.json").exists())
        self.assertTrue((self.out/"double_review_receipt.json").is_file())
        self.assertEqual(original_head, cmd(self.repo, "rev-parse", "HEAD"))
        self.assertEqual("", cmd(self.repo, "status", "--porcelain"))

    def test_version_tokens_are_hints_not_proof(self):
        self.assertEqual([1, 100, 205], audit.version_tokens("V1 V100 v0205 V0 V10000", 205))
        self.assertEqual([], audit.version_tokens("vhost V01X", 205))
        self.assertEqual(64, len(hashlib.sha256(audit.canonical({"a": 1})).hexdigest()))


if __name__ == "__main__":
    unittest.main()
