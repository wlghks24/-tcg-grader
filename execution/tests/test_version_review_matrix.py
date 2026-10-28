"""Evidence-ledger regressions: 100-version boundaries never imply code approval."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import version_review_matrix as audit
from version_window_audit import SCHEMA, canonical_sha256

HEAD = "a" * 40


class EvidenceReviewTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def checkpoint(self, start, previous=None, paths=None, commits=None):
        paths = paths if paths is not None else []
        commits = commits if commits is not None else []
        versions = sorted({
            v for row in paths + commits for v in row["tokens"]
        })
        d = {
            "schema": SCHEMA, "window": {"start": start, "end": start+99},
            "source": {"head": HEAD, "is_shallow": False, "history_limited": False},
            "previous_checkpoint_sha256": previous,
            "candidate_version_tokens": versions,
            "path_hints": paths, "commit_subject_hints": commits,
            "excluded_cross_project_paths": 0, "unsafe_versioned_paths": 0,
            "carry_forward": [], "status": "INVENTORY_ONLY_NOT_RELEASE_VERIFIED",
            "tests": "NOT_RUN", "device": "DEVICE_UNVERIFIED", "score": None,
        }
        d["checkpoint_sha256"] = canonical_sha256(d)
        return d

    def store(self, data):
        n = data["window"]["start"]
        path = self.root / f"window_v{n:03d}_v{n+99:03d}.json"
        path.write_text(json.dumps(data, sort_keys=True), encoding="utf-8")
        return path

    def build_windows(self, latest=879):
        prev = None
        for start in range(1, latest+1, 100):
            paths = []
            commits = []
            if start == 1:
                paths = [
                    {"path": "grading_accuracy_v99.py", "tokens": [99],
                     "git_blob": "c"*40, "classification": "filename_hint_only"},
                    {"path": "test_example_v99.py", "tokens": [99],
                     "git_blob": "d"*40, "classification": "filename_hint_only"},
                ]
            if start == 801:
                commits = [
                    {"commit": "e"*40, "tokens": [879],
                     "subject": "V879 proposed", "classification": "commit_subject_hint_only"}
                ]
            data = self.checkpoint(start, previous=prev, paths=paths, commits=commits)
            self.store(data)
            prev = data["checkpoint_sha256"]

    def test_all_nine_windows_and_exact_final_partial_boundary(self):
        self.build_windows()
        output = audit.build(self.root, end_version=879, expected_head=HEAD)
        self.assertEqual(879, len(output["version_reviews"]))
        self.assertEqual(9, len(output["window_reviews"]))
        self.assertEqual((801,879), (output["window_reviews"][-1]["first"],
                                    output["window_reviews"][-1]["last"]))
        self.assertEqual(79, output["window_reviews"][-1]["numeric_slots"])
        self.assertIsNone(output["quality_score"])
        self.assertEqual(0, output["reviewed_versions"])
        self.assertNotIn(880, {r["version"] for r in output["version_reviews"]})

    def test_filename_test_and_commit_are_only_leads(self):
        self.build_windows()
        output = audit.build(self.root, end_version=879, expected_head=HEAD)
        one = output["version_reviews"][98]
        self.assertEqual(99, one["version"])
        self.assertEqual(["grading_accuracy_v99.py"], one["source_filename_hints"])
        self.assertEqual(["test_example_v99.py"], one["test_filename_hints"])
        self.assertEqual("LEADS_ONLY_NOT_REVIEWED", one["evidence_state"])
        self.assertIsNone(one["quality_score"])
        self.assertEqual("NOT_VERIFIED", one["current_head_behavior_tests"])

    def test_empty_v701_v800_does_not_mean_versions_absent(self):
        self.build_windows()
        report = audit.build(self.root, end_version=879, expected_head=HEAD)
        group = report["window_reviews"][7]
        self.assertEqual(100, group["slots_without_main_token_lead"])
        self.assertEqual("NOT_AUDITED", group["result"])
        self.assertEqual("NO_MAIN_TOKEN_LEAD", report["version_reviews"][700]["evidence_state"])

    def test_tampered_digest_is_rejected(self):
        self.build_windows()
        p = self.root/"window_v201_v300.json"
        data = json.loads(p.read_text("utf-8"))
        data["source"]["head"] = "b"*40
        p.write_text(json.dumps(data), "utf-8")
        with self.assertRaisesRegex(ValueError, "source_head_mismatch"):
            audit.build(self.root, end_version=879, expected_head=HEAD)

    def test_forged_previous_checkpoint_is_rejected(self):
        self.build_windows()
        p = self.root/"window_v101_v200.json"
        d = json.loads(p.read_text("utf-8"))
        d["previous_checkpoint_sha256"] = "0"*64
        d["checkpoint_sha256"] = canonical_sha256(d)
        p.write_text(json.dumps(d), "utf-8")
        with self.assertRaisesRegex(ValueError, "broken_predecessor_link"):
            audit.build(self.root, end_version=879, expected_head=HEAD)

    def test_claimed_green_tests_or_grade_is_refused(self):
        self.build_windows()
        p = self.root/"window_v001_v100.json"
        d = json.loads(p.read_text("utf-8"))
        d["tests"] = "PASS"
        d["score"] = 100
        d["checkpoint_sha256"] = canonical_sha256(d)
        p.write_text(json.dumps(d), "utf-8")
        with self.assertRaisesRegex(ValueError, "unsupported_claim_of_verification"):
            audit.build(self.root, end_version=879, expected_head=HEAD)

    def test_unsupported_candidate_token_is_rejected(self):
        self.build_windows()
        p = self.root/"window_v101_v200.json"
        d = json.loads(p.read_text("utf-8"))
        d["candidate_version_tokens"] = [150]
        d["checkpoint_sha256"] = canonical_sha256(d)
        p.write_text(json.dumps(d), "utf-8")
        with self.assertRaisesRegex(ValueError, "candidate_tokens_not_supported"):
            audit.build(self.root, end_version=879, expected_head=HEAD)

    def test_shallow_or_truncated_history_cannot_pass(self):
        self.build_windows()
        p = self.root/"window_v601_v700.json"
        d = json.loads(p.read_text("utf-8"))
        d["source"]["history_limited"] = True
        d["checkpoint_sha256"] = canonical_sha256(d)
        p.write_text(json.dumps(d), "utf-8")
        with self.assertRaisesRegex(ValueError, "incomplete_git_history"):
            audit.build(self.root, end_version=879, expected_head=HEAD)

    def test_duplicate_json_keys_and_symlink_block(self):
        self.build_windows()
        p = self.root/"window_v001_v100.json"
        p.write_text('{"schema":1,"schema":2}', "utf-8")
        with self.assertRaisesRegex(ValueError, "duplicate_json_key"):
            audit.build(self.root, end_version=879, expected_head=HEAD)
        p.unlink()
        p.symlink_to(self.root/"window_v101_v200.json")
        with self.assertRaisesRegex(ValueError, "unsafe_window_checkpoint"):
            audit.build(self.root, end_version=879, expected_head=HEAD)

    def test_missing_window_and_invalid_latest_hold(self):
        self.build_windows()
        (self.root/"window_v301_v400.json").unlink()
        with self.assertRaisesRegex(ValueError, "unsafe_window_checkpoint"):
            audit.build(self.root, end_version=879, expected_head=HEAD)
        with self.assertRaisesRegex(ValueError, "invalid_last_version"):
            audit.build(self.root, end_version=0, expected_head=HEAD)

    def test_read_only_status_no_changes(self):
        self.build_windows()
        before = [(p.name, p.read_bytes()) for p in sorted(self.root.iterdir())]
        audit.build(self.root, end_version=879, expected_head=HEAD)
        after = [(p.name, p.read_bytes()) for p in sorted(self.root.iterdir())]
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
