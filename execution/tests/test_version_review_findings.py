"""Git-object anchored findings and cross-window carry-forward regression checks."""
from __future__ import annotations

import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import version_review_findings as f


class ReviewedFindingsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.run_git("init", "-q")
        self.run_git("config", "user.name", "Fixture Auditor")
        self.run_git("config", "user.email", "auditor@example.invalid")
        self.file = self.root / "grading_accuracy_v99.py"
        self.file.write_text("def combine_defect_risk(): return 100\n", "utf-8")
        self.run_git("add", "-A")
        self.run_git("commit", "-qm", "V99 original fixture")
        self.base = self.run_git("rev-parse", "HEAD")
        blob = self.run_git("rev-parse", "HEAD:grading_accuracy_v99.py")
        self.findings = [
            dict(id="W001-F006", first_observed_version=99,
                 related_versions=[99, 291], severity="P0",
                 state="HISTORICAL_REPAIR_EVIDENCED",
                 summary="Verified historical missing-channel guard was repaired",
                 source_refs=[{"path": "grading_accuracy_v99.py", "blob": blob}],
                 code_history=[self.base], tests=["test_v99.py"],
                 candidate_pr=None, quality_score=None,
                 physical_tablet_verified=False, note="History only; not full version QA"),
            dict(id="W001-F009", first_observed_version=99,
                 related_versions=[99, 291, 426], severity="P0",
                 state="PATCH_CANDIDATE_BLOCKED",
                 summary="Negative defect evidence candidate is not approved",
                 source_refs=[{"path": "grading_accuracy_v99.py", "blob": blob}],
                 code_history=[], tests=["test_v99.py"],
                 candidate_pr=903, quality_score=None,
                 physical_tablet_verified=False, note="Requires reviewed successor"),
            dict(id="W701-F001", first_observed_version=701,
                 related_versions=[701, 800], severity="P1",
                 state="PROVENANCE_NOT_VERIFIED",
                 summary="Evidence gap in later version naming and origination",
                 source_refs=[], code_history=[], tests=[], candidate_pr=None,
                 quality_score=None, physical_tablet_verified=False,
                 note="No exact original evidence is asserted"),
        ]
        self.ledger = {
            "schema": f.SCHEMA, "baseline_main_sha": self.base,
            "scope": "selected_confirmed_or_pending_findings_only_not_complete_879_review",
            "findings": self.findings,
        }

    def run_git(self, *args):
        return subprocess.check_output(["git", *args], cwd=self.root, text=True).strip()

    def check(self, ledger=None, *, latest=879):
        return f.validate(ledger if ledger is not None else self.ledger,
                          self.root, head=self.base, latest=latest)

    def test_referenced_tests_do_not_fake_executed_evidence(self):
        result = self.check()
        self.assertEqual(2, result["test_reference_missing_in_checked_head"])
        self.assertFalse(result["test_references_are_execution_proof"])
        self.assertEqual(
            {"NOT_IN_CHECKED_HEAD"},
            {r["state"] for r in result["test_reference_paths"]},
        )
        self.assertIsNone(result["quality_score"])

    def test_referenced_test_blob_presence_still_is_not_test_pass(self):
        (self.root / "test_v99.py").write_text(
            "def test_fixture(): assert True\n", encoding="utf-8")
        self.run_git("add", "test_v99.py")
        self.run_git("commit", "-qm", "fixture test source")
        head = self.run_git("rev-parse", "HEAD")
        result = f.validate(self.ledger, self.root, head=head)
        self.assertEqual(0, result["test_reference_missing_in_checked_head"])
        self.assertEqual(
            {"PRESENT_AS_GIT_BLOB_NOT_EXECUTION_PROOF"},
            {r["state"] for r in result["test_reference_paths"]},
        )
        self.assertFalse(result["test_references_are_execution_proof"])
        self.assertEqual(0, result["complete_version_reviews"])

    def test_untrusted_test_reference_path_and_symlink_are_blocked(self):
        with self.assertRaisesRegex(ValueError, "unsafe_test_reference_path"):
            f.test_reference_status(self.root, self.base, "../test_v99.py")
        self.run_git("config", "core.symlinks", "true")
        (self.root / "test_v99.py").symlink_to("grading_accuracy_v99.py")
        self.run_git("add", "test_v99.py")
        self.run_git("commit", "-qm", "fixture test symlink")
        head = self.run_git("rev-parse", "HEAD")
        with self.assertRaisesRegex(ValueError, "unsafe_test_reference_object"):
            f.validate(self.ledger, self.root, head=head)

    def test_nine_window_carry_forward_never_closes_pending(self):
        result = self.check()
        self.assertEqual(9, len(result["window_carry_forward"]))
        self.assertEqual(0, result["complete_version_reviews"])
        self.assertFalse(result["release_approval"])
        self.assertIsNone(result["quality_score"])
        self.assertEqual(
            ["W001-F009"],
            result["window_carry_forward"][6]["open_carry_forward_ids"],
        )
        self.assertEqual(
            ["W001-F009", "W701-F001"],
            result["window_carry_forward"][8]["open_carry_forward_ids"],
        )
        self.assertEqual(
            ["W001-F006"],
            result["window_carry_forward"][8]["historical_repair_record_ids"],
        )

    def test_blocked_patch_cannot_claim_success(self):
        altered = copy.deepcopy(self.ledger)
        altered["findings"][1]["quality_score"] = 100
        with self.assertRaisesRegex(ValueError, "unsupported_quality_or_device_claim"):
            self.check(altered)
        altered = copy.deepcopy(self.ledger)
        altered["findings"][1]["physical_tablet_verified"] = True
        with self.assertRaisesRegex(ValueError, "unsupported_quality_or_device_claim"):
            self.check(altered)

    def test_duplicate_identifier_rejected(self):
        altered = copy.deepcopy(self.ledger)
        altered["findings"].append(copy.deepcopy(altered["findings"][1]))
        with self.assertRaisesRegex(ValueError, "invalid_or_duplicate_finding_id"):
            self.check(altered)

    def test_bad_baseline_blob_is_rejected(self):
        altered = copy.deepcopy(self.ledger)
        altered["findings"][0]["source_refs"][0]["blob"] = "f"*40
        with self.assertRaisesRegex(ValueError, "baseline_source_blob_changed"):
            self.check(altered)

    def test_directory_escape_and_symlink_rejected(self):
        with self.assertRaisesRegex(ValueError, "unsafe_evidence_path"):
            f.baseline_blob(self.root, self.base, "../grading_accuracy_v99.py")
        with self.assertRaisesRegex(ValueError, "unsafe_evidence_path"):
            f.baseline_blob(self.root, self.base, "/etc/passwd")
        self.run_git("config", "core.symlinks", "true")
        (self.root / "danger.py").symlink_to("grading_accuracy_v99.py")
        self.run_git("add", "danger.py")
        self.run_git("commit", "-qm", "symlink fixture")
        with self.assertRaisesRegex(ValueError, "unsafe_baseline_source_type"):
            f.baseline_blob(self.root, self.run_git("rev-parse", "HEAD"), "danger.py")

    def test_earliest_version_identifier_must_match_window(self):
        altered = copy.deepcopy(self.ledger)
        altered["findings"][0]["first_observed_version"] = 101
        with self.assertRaisesRegex(ValueError, "invalid_or_duplicate_finding_id"):
            self.check(altered)

    def test_unverified_provenance_does_not_require_fake_file(self):
        result = self.check()
        self.assertIn("W701-F001", result["window_carry_forward"][7]["open_carry_forward_ids"])
        self.assertEqual("DEVICE_UNVERIFIED", result["device"])

    def test_unknown_state_and_unreviewed_candidate_fail_closed(self):
        altered = copy.deepcopy(self.ledger)
        altered["findings"][1]["state"] = "APPROVED"
        with self.assertRaisesRegex(ValueError, "invalid_finding_state"):
            self.check(altered)
        altered = copy.deepcopy(self.ledger)
        altered["findings"][1]["candidate_pr"] = None
        with self.assertRaisesRegex(ValueError, "blocked_candidate_without_pr"):
            self.check(altered)

    def test_duplicate_json_and_symlink_document_rejected(self):
        path = self.root / "ledger.json"
        path.write_text('{"schema":1,"schema":2}', "utf-8")
        with self.assertRaisesRegex(ValueError, "duplicate_findings_json_key"):
            f.read_json(path)
        path.unlink()
        path.symlink_to(self.file)
        with self.assertRaisesRegex(ValueError, "unsafe_findings_source"):
            f.read_json(path)

    def test_nonancestor_evidence_ref_fails(self):
        self.run_git("checkout", "--orphan", "unrelated")
        self.run_git("rm", "-rf", ".")
        (self.root/"new.txt").write_text("independent root", "utf-8")
        self.run_git("add", "-A")
        self.run_git("commit", "-qm", "unrelated branch")
        diverged = self.run_git("rev-parse", "HEAD")
        with self.assertRaisesRegex(ValueError, "git_evidence_unavailable"):
            f.validate(self.ledger, self.root, head=diverged)

    def test_validation_does_not_write_worktree_files(self):
        before=self.run_git("status", "--porcelain")
        self.check()
        after=self.run_git("status", "--porcelain")
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
