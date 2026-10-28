"""Strict W001→W801 defect/provenance handoff tests; no release approval."""
from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from execution import version_review_findings as f

ROOT = Path(__file__).resolve().parents[2]
LEDGER = ROOT / "docs/tablet/V001_V879_CONTINUITY_FINDINGS.json"


class EvidenceHandoffsTests(unittest.TestCase):
    def setUp(self):
        self.data = f.load(LEDGER)

    def test_nine_windows_and_latest_partial_boundary(self):
        result = f.build(self.data)
        self.assertEqual(9, len(result["windows"]))
        self.assertEqual((801, 879), (result["windows"][-1]["first"], result["windows"][-1]["last"]))
        self.assertEqual(5, result["total_findings"])
        self.assertIsNone(result["quality_score"])
        self.assertIs(result["physical_tablet_verified"], False)

    def test_w001_candidates_carry_to_w101(self):
        result = f.build(self.data)
        w1, w101 = result["windows"][:2]
        self.assertEqual(["W001-F001", "W001-F006", "W001-F009"],
                         w1["unresolved_carry_forward"])
        self.assertEqual(["W001-F001", "W001-F006", "W001-F009", "W101-F005"],
                         w101["unresolved_carry_forward"])

    def test_v291_historical_repair_kept_but_no_longer_open(self):
        rows = f.build(self.data)["windows"]
        self.assertEqual(["W001-F006"], rows[2]["historical_resolutions_in_window"])
        self.assertNotIn("W001-F006", rows[2]["unresolved_carry_forward"])
        self.assertIn("W001-F009", rows[2]["unresolved_carry_forward"])

    def test_v701_provenance_gap_never_treated_as_missing_releases(self):
        rows = f.build(self.data)["windows"]
        self.assertIn("W701-F001", rows[7]["unresolved_carry_forward"])
        self.assertIn("W701-F001", rows[8]["unresolved_carry_forward"])
        self.assertEqual("REVIEW_FINDINGS_NOT_RELEASE_APPROVAL", rows[7]["status"])

    def test_final_open_defect_ids_not_approved(self):
        result = f.build(self.data)
        self.assertEqual(["W001-F001", "W001-F009", "W101-F005", "W701-F001"],
                         result["open_at_latest"])
        self.assertEqual("UNRESOLVED_REVIEW_GAPS_HOLD", result["status"])

    def test_no_fabricated_score_or_device_receipt(self):
        bad = copy.deepcopy(self.data)
        bad["findings"][0]["score"] = 95
        with self.assertRaisesRegex(ValueError, "unverified_quality"):
            f.build(bad)
        bad = copy.deepcopy(self.data)
        bad["device_verified"] = True
        with self.assertRaisesRegex(ValueError, "unsupported_release_or_device"):
            f.build(bad)

    def test_duplicate_finding_id_rejected(self):
        bad = copy.deepcopy(self.data)
        bad["findings"].append(copy.deepcopy(bad["findings"][0]))
        with self.assertRaisesRegex(ValueError, "invalid_or_duplicate_finding_id"):
            f.build(bad)

    def test_resolution_must_match_historical_state(self):
        bad = copy.deepcopy(self.data)
        bad["findings"][1]["resolved_in"] = None
        with self.assertRaisesRegex(ValueError, "resolution_state_contradiction"):
            f.build(bad)
        bad = copy.deepcopy(self.data)
        bad["findings"][1]["resolved_in"] = 1
        with self.assertRaisesRegex(ValueError, "invalid_resolution_version"):
            f.build(bad)

    def test_finding_window_and_version_invalid_rejected(self):
        bad = copy.deepcopy(self.data)
        bad["findings"][0]["id"] = "W101-F001"
        with self.assertRaisesRegex(ValueError, "finding_id_wrong_window"):
            f.build(bad)
        bad = copy.deepcopy(self.data)
        bad["findings"][0]["opened_at"] = True
        with self.assertRaisesRegex(ValueError, "invalid_opened_version"):
            f.build(bad)

    def test_source_sha_and_version_claims_must_be_sound(self):
        bad = copy.deepcopy(self.data)
        bad["findings"][1]["source_commits"][0] = "not-a-sha"
        with self.assertRaisesRegex(ValueError, "invalid_evidence_sha"):
            f.build(bad)
        bad = copy.deepcopy(self.data)
        bad["findings"][1]["related_versions"] = [99, 99, 291]
        with self.assertRaisesRegex(ValueError, "invalid_related_versions"):
            f.build(bad)

    def test_reject_duplicate_json_and_symlink_then_preserve_bytes(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            p = base / "findings.json"
            p.write_text('{"schema":1,"schema":2}', "utf-8")
            with self.assertRaisesRegex(ValueError, "duplicate_json_key"):
                f.load(p)
            p.unlink()
            p.symlink_to(LEDGER)
            with self.assertRaisesRegex(ValueError, "unsafe_findings_source"):
                f.load(p)
        original = LEDGER.read_bytes()
        f.build(self.data)
        self.assertEqual(original, LEDGER.read_bytes())


if __name__ == "__main__":
    unittest.main()
