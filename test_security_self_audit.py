import os
import tempfile
import unittest
from pathlib import Path

import security_self_audit as audit


class SecuritySelfAuditTests(unittest.TestCase):
    def test_scan_keeps_syntax_and_dangerous_call_detection(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "safe.py").write_text("VALUE = 1\n", encoding="utf-8")
            (root / "danger.py").write_text("eval(  # review\n'1 + 1')\n", encoding="utf-8")
            (root / "broken.py").write_text("def broken(:\n", encoding="utf-8")
            findings = audit.scan_repository(root)

        rules_by_path = {(row["path"], row["rule"]) for row in findings}
        self.assertIn(("danger.py", "PY_DANGEROUS_EXEC"), rules_by_path)
        self.assertIn(("broken.py", "PY_SYNTAX"), rules_by_path)
        self.assertNotIn(("safe.py", "PY_SYNTAX"), rules_by_path)

    def test_excluded_and_symlinked_directories_are_not_descended(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            excluded = root / "node_modules"
            excluded.mkdir()
            (excluded / "ignored.py").write_text("eval('1')\n", encoding="utf-8")
            real = root / "external"
            real.mkdir()
            (real / "visible.py").write_text("VALUE = 1\n", encoding="utf-8")
            link = root / "linked"
            try:
                os.symlink(real, link, target_is_directory=True)
            except (OSError, NotImplementedError):
                link = None

            scanned = {path.relative_to(root).as_posix() for path, _ in audit.iter_text_files(root)}

        self.assertNotIn("node_modules/ignored.py", scanned)
        if link is not None:
            self.assertNotIn("linked/visible.py", scanned)
        self.assertIn("external/visible.py", scanned)


if __name__ == "__main__":
    unittest.main()
