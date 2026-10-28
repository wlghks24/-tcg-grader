"""Read-only pinned-main checks: V101-V109 verifier scripts are NOT inventory commands."""
from __future__ import annotations

import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASE_MAIN = "6c78831bbb6e188717f86ef90243a836d2e0b67a"


def historical_source(path: str) -> str:
    # Read an immutable Git object. Do NOT import or execute legacy verify scripts.
    return subprocess.check_output(
        ["git", "show", f"{BASE_MAIN}:{path}"],
        cwd=ROOT, text=True, timeout=25,
    )


class LegacyVerifierReplayRestrictionsTests(unittest.TestCase):
    def test_v101_can_launch_server_and_write_verification_report(self):
        code = historical_source("verify_v101_final.py")
        self.assertIn("compileall.compile_dir", code)
        self.assertIn("subprocess.Popen", code)
        self.assertIn("127.0.0.1:8765", code)
        self.assertIn("V101_FINAL_VERIFICATION_REPORT.json", code)
        self.assertIn(".write_text(", code)

    def test_v102_chains_v101_and_writes_its_own_report(self):
        code = historical_source("verify_v102_final.py")
        self.assertIn("verify_v101_final.py", code)
        self.assertIn("verify_v99_cross_runtime.py", code)
        self.assertIn("V102_FINAL_VERIFICATION_REPORT.json", code)
        self.assertIn(".write_text(", code)

    def test_v103_chains_v102_and_writes_its_own_report(self):
        code = historical_source("verify_v103_final.py")
        self.assertIn("verify_v102_final.py", code)
        self.assertIn("V103_FINAL_VERIFICATION_REPORT.json", code)
        self.assertIn(".write_text(", code)

    def test_v109_runs_v108_and_writes_its_own_report(self):
        code = historical_source("verify_v109_final.py")
        self.assertIn("verify_v108_final.py", code)
        self.assertIn("V109_FINAL_VERIFICATION_REPORT.json", code)
        self.assertIn("REPORT.write_text(", code)


if __name__ == "__main__":
    unittest.main()
