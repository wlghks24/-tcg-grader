"""Regression tests for the external skill read-only scanner."""
import importlib.util
import tempfile
import unittest
from pathlib import Path

MODULE = Path(__file__).resolve().parents[1] / "external_skill_review.py"
spec = importlib.util.spec_from_file_location("external_skill_review", MODULE)
scanner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scanner)


class ReviewTests(unittest.TestCase):
    def test_duplicate_and_ui_candidates(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "a.py").write_text("def alpha(x):\n    a = x + 1\n    b = a * 2\n    return b\n")
            (root / "b.py").write_text("def beta(x):\n    a = x + 1\n    b = a * 2\n    return b\n")
            (root / "index.html").write_text("<html><img src='x.png'></html>")
            result = scanner.audit(root)
            kinds = {item["kind"] for item in result["findings"]}
            self.assertIn("duplicate_candidate", kinds)
            self.assertIn("viewport_review", kinds)
            self.assertIn("image_alt_review", kinds)
            self.assertFalse(result["device_verified"])

    def test_does_not_follow_symlink_or_execute_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            marker = root / "executed"
            (root / "unsafe.py").write_text("open(" + repr(str(marker)) + ", 'w').write('bad')\n")
            (root / "alias.py").symlink_to(root / "unsafe.py")
            result = scanner.audit(root)
            self.assertEqual(result["inspected_files"], 1)
            self.assertFalse(marker.exists())

    def test_invalid_python_is_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "bad.py").write_text("def broken(:\n")
            self.assertEqual(scanner.audit(root)["findings"][0]["kind"], "python_syntax")


if __name__ == "__main__":
    unittest.main()
