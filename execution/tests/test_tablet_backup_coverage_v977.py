"""Offline tests for read-only V977 backup coverage inventory."""
import tempfile
import unittest
from pathlib import Path
from execution.tablet_backup_coverage_v977 import audit


class CoverageTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.repo = Path(temp.name) / "repo"
        self.repo.mkdir()
        (self.repo / ".git").mkdir()

    def test_nested_photos_and_models_flag_missing_coverage(self):
        (self.repo / "state.json").write_text("{}")
        for name in ("photos/card.jpg", "models/network.bin", "learning/labels.json"):
            p = self.repo / name
            p.parent.mkdir(exist_ok=True)
            p.write_bytes(b"data")
        result = audit(self.repo)
        self.assertEqual(result["counts"], {"root_json": 1, "nested_data": 3})
        self.assertIn("NESTED_DATA_NOT_COVERED_BY_V976_ROOT_JSON_BACKUP", result["reasons"])
        self.assertFalse(result["files_written"])

    def test_symlink_never_followed(self):
        outside = self.repo.parent / "private"
        outside.write_text("private")
        (self.repo / "photos").symlink_to(outside)
        self.assertIn("SYMLINK_REQUIRES_REVIEW", audit(self.repo)["reasons"])

    def test_stable_fingerprint_and_no_modifications(self):
        p = self.repo / "model" / "weights.bin"
        p.parent.mkdir()
        p.write_bytes(b"abc")
        before = p.stat().st_mtime_ns
        a = audit(self.repo)
        b = audit(self.repo)
        self.assertEqual(a["inventory_sha256"], b["inventory_sha256"])
        self.assertEqual(before, p.stat().st_mtime_ns)
        self.assertEqual(a["status"], "HOLD_NO_DEVICE_ACTION")

    def test_limit_fails_closed(self):
        (self.repo / "a.json").write_text("{}")
        (self.repo / "b.json").write_text("{}")
        self.assertIn("INVENTORY_LIMIT_EXCEEDED", audit(self.repo, max_files=1)["reasons"])

    def test_non_repo_rejected(self):
        with self.assertRaises(ValueError):
            audit(self.repo.parent)


if __name__ == "__main__":
    unittest.main()
