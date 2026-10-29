"""Strict per-window survey -> remediation -> after-recheck must HOLD if unproved."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pc_auditor"))
from audit import AuditError, read_checkpoint
from window_cycle import run_strict_cycle


def git(repo, *args):
    return subprocess.run(["git", *args], cwd=repo, capture_output=True,
                          check=True).stdout.decode("utf-8").strip()


class StrictWindowCycleTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="tcg-strict-v05-")
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.repo = self.root / "tcg"
        self.repo.mkdir()
        git(self.repo, "init", "-q")
        git(self.repo, "config", "user.email", "audit@example.invalid")
        git(self.repo, "config", "user.name", "Audit")
        (self.repo / "V040_grade.py").write_text(
            "def grade(row):\n    return bool(row.get('verified',False))\n")
        (self.repo / "V101_next.py").write_text("def next():\n    return 1\n")
        path = self.repo / "execution" / "evidence"
        path.mkdir(parents=True)
        (path / "version_review_findings_v001_v205.json").write_text(json.dumps({
            "findings": [{"id":"W001-F015", "first_observed_version":40,
                          "state":"OPEN_SUCCESSOR_REQUIRED", "severity":"P0",
                          "summary":"Unverified grading source"}]}))
        git(self.repo, "add", ".")
        git(self.repo, "commit", "-qm", "V40 V101 source hints only")
        self.output = self.root / "reports"

    def _folder(self):
        return next(self.output.iterdir())

    def test_korean_design_covers_every_slot_and_holds_unverified_tasks(self):
        run_strict_cycle(self.repo, self.output, latest=205)
        folder = self._folder() / "window_remediation_V0001_V0100"
        design = read_checkpoint(folder / "구간별_한글_기획설계.json")
        report = (folder / "구간별_한글_기획설계.md").read_text("utf-8")
        self.assertEqual(100, len(design["slots"]))
        self.assertEqual(list(range(1, 101)), [x["version"] for x in design["slots"]])
        self.assertIsNone(design["quality_score"])
        self.assertFalse(design["next_window_allowed"])
        self.assertIn("verified", report)
        self.assertIn("번호 단서 없음", report)
        self.assertEqual("", git(self.repo, "status", "--porcelain"))
        with self.assertRaisesRegex(AuditError, "korean_design_report_tampered"):
            (folder / "구간별_한글_기획설계.md").write_text("검증완료", encoding="utf-8")
            run_strict_cycle(self.repo, self.output, latest=205)

    def test_auto_stops_at_first_100_even_if_inventory_passes(self):
        head_before = git(self.repo, "rev-parse", "HEAD")
        status = run_strict_cycle(self.repo, self.output, latest=205)
        self.assertFalse(status["next_window_allowed"])
        self.assertEqual(1, status["investigated_windows"])
        self.assertEqual(0, status["completed_remediated_windows"])
        folder = self._folder()
        self.assertTrue((folder / "V0001_V0100.json").is_file())
        self.assertTrue((folder / "crosscheck_V0001_V0100.json").is_file())
        self.assertFalse((folder / "V0101_V0200.json").exists())
        gate = read_checkpoint(folder / "window_remediation_V0001_V0100" / "window_gate.json")
        self.assertEqual("HOLD_REMEDIATION_AND_HISTORICAL_EVIDENCE_UNVERIFIED", gate["status"])
        self.assertFalse(gate["next_window_allowed"])
        self.assertEqual(98, len(gate["missing_hint_slots_not_proven_absent_releases"]))
        self.assertEqual(2, len(gate["hint_only_slots_not_verified_releases"]))
        self.assertEqual(["W001-F015"], gate["open_findings_carry_forward"])
        self.assertEqual(1, len(gate["before_after_candidates"]))
        candidate = gate["before_after_candidates"][0]
        self.assertNotEqual(candidate["before_git_blob_sha256"],
                            candidate["after_isolated_candidate_sha256"])
        self.assertEqual("PASS", candidate["independent_static_recheck"])
        self.assertEqual("PASS", candidate["negative_input_recheck"])
        self.assertFalse(candidate["patch_applied_to_original"])
        self.assertEqual(head_before, git(self.repo, "rev-parse", "HEAD"))
        self.assertEqual("", git(self.repo, "status", "--porcelain"))

    def test_resume_retests_same_window_without_creating_next(self):
        first = run_strict_cycle(self.repo, self.output, latest=205)
        second = run_strict_cycle(self.repo, self.output, latest=205)
        self.assertEqual(first, second)
        self.assertFalse((self._folder() / "V0101_V0200.json").exists())
        gate_dir = self._folder() / "window_remediation_V0001_V0100"
        self.assertEqual(1, len(list((gate_dir / "repair_candidates").glob("*.patch"))))

    def test_tampered_gate_seal_refuses_resume(self):
        run_strict_cycle(self.repo, self.output, latest=205)
        f = self._folder() / "window_remediation_V0001_V0100" / "window_gate.json"
        row = read_checkpoint(f)
        row["next_window_allowed"] = True
        f.write_text(json.dumps(row), encoding="utf-8")
        with self.assertRaisesRegex(AuditError, "report|tamper|differs|existing"):
            run_strict_cycle(self.repo, self.output, latest=205)
        self.assertFalse((self._folder() / "V0101_V0200.json").exists())

    def test_changed_patch_refuses_resume_no_silent_overwrite(self):
        run_strict_cycle(self.repo, self.output, latest=205)
        patch = next((self._folder() / "window_remediation_V0001_V0100" /
                      "repair_candidates").glob("*.patch"))
        patch.write_text("forged", encoding="utf-8")
        with self.assertRaisesRegex(AuditError, "existing_patch_tampered"):
            run_strict_cycle(self.repo, self.output, latest=205)
        self.assertFalse((self._folder() / "V0101_V0200.json").exists())

    def test_without_automatic_patch_still_holds_missing_evidence(self):
        (self.repo / "V040_grade.py").write_text("def grade(row):\n    return row.get('verified') is True\n")
        git(self.repo, "add", ".")
        git(self.repo, "commit", "-qm", "fix current flag but history missing")
        status=run_strict_cycle(self.repo, self.output, 205)
        self.assertFalse(status["next_window_allowed"])
        gate=read_checkpoint(self._folder()/"window_remediation_V0001_V0100"/"window_gate.json")
        self.assertEqual([], gate["before_after_candidates"])
        self.assertGreater(len(gate["missing_hint_slots_not_proven_absent_releases"]),0)

    def test_legacy_multiwindow_inventory_cannot_skip_gate(self):
        import audit
        audit.run_audit(self.repo, self.output, latest=205, auto_review=False)
        with self.assertRaisesRegex(AuditError, "legacy_multiwindow"):
            run_strict_cycle(self.repo, self.output, 205)

    def test_forged_gate_and_recomputed_digest_still_hold(self):
        from audit import atomic_json, digest
        run_strict_cycle(self.repo, self.output, latest=205)
        gate_path=self._folder()/"window_remediation_V0001_V0100"/"window_gate.json"
        row=read_checkpoint(gate_path)
        row["next_window_allowed"]=True
        row["status"]="FAKE_APPROVED"
        row["gate_sha256"]=digest({k:v for k,v in row.items() if k!="gate_sha256"})
        atomic_json(gate_path,row)
        with self.assertRaisesRegex(AuditError,"report|tamper|differs|existing"):
            run_strict_cycle(self.repo,self.output,205)
        self.assertFalse((self._folder()/"V0101_V0200.json").exists())

    def test_modified_staged_after_file_blocks_recheck(self):
        run_strict_cycle(self.repo,self.output,205)
        root=self._folder()/"window_remediation_V0001_V0100"
        validated=read_checkpoint(root/"candidate_validation.json")
        staged=root/validated["staged"][0]["staged_copy"]
        staged.write_bytes(staged.read_bytes()+b"\nprint('unexpected')\n")
        with self.assertRaisesRegex(AuditError,"candidate|staged|tamper|mismatch"):
            run_strict_cycle(self.repo,self.output,205)
        self.assertFalse((self._folder()/"V0101_V0200.json").exists())

    def test_gui_or_cli_style_does_not_create_next_window_on_hold(self):
        script=Path(__file__).resolve().parents[1]/"pc_auditor"/"audit.py"
        for opt in ([],["--auto"]):
            out=self.root/("run_auto" if opt else "run_default")
            p=subprocess.run([sys.executable,str(script),"--repo",str(self.repo),
                "--latest","205","--output",str(out),*opt],capture_output=True,text=True)
            self.assertEqual(2,p.returncode,p.stderr)
            self.assertIn("next 100 blocked",p.stdout)
            folder=next(out.iterdir())
            self.assertFalse((folder/"V0101_V0200.json").exists())


if __name__ == "__main__":
    unittest.main()
