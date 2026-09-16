import json
import subprocess
import unittest
from pathlib import Path


class DashboardVerifiedBoundaryV246Tests(unittest.TestCase):
    def test_only_current_conflict_free_official_result_is_verified(self):
        source = Path("graded_photo_dashboard.js").read_text(encoding="utf-8")
        functions = "\n".join(
            line
            for line in source.splitlines()
            if line.startswith(("function statusOf(", "function isVerified("))
        )
        self.assertIn("function statusOf(", functions)
        self.assertIn("function isVerified(", functions)

        rows = [
            {"status": "공식검증 대기"},
            {"verified": True},
            {"official_verified": True},
            {"status": "verified_reference", "official_result": False},
            {"official_result": True, "manual_official_verification_required": True},
            {"official_result": True, "evidence_conflicts": ["grade_conflict"]},
            {"official_result": True, "status": "quarantine"},
            {"official_result": True},
            {
                "official_result": True,
                "manual_official_verification_required": False,
                "evidence_conflicts": [],
                "status": "verified_reference",
            },
        ]
        script = (
            functions
            + "\nconsole.log(JSON.stringify("
            + json.dumps(rows, ensure_ascii=False)
            + ".map(isVerified)));"
        )
        output = subprocess.check_output(["node", "-e", script], text=True)
        self.assertEqual(
            json.loads(output),
            [False, False, False, False, False, False, False, True, True],
        )

    def test_legacy_string_and_boolean_shortcuts_are_absent(self):
        source = Path("graded_photo_dashboard.js").read_text(encoding="utf-8")
        line = next(line for line in source.splitlines() if line.startswith("function isVerified("))
        self.assertNotIn("s.includes('공식검증')", line)
        self.assertNotIn("r.verified===true", line)
        self.assertNotIn("r.official_verified===true", line)
        self.assertIn("r.official_result===true", line)
        self.assertIn("manual_official_verification_required", line)
        self.assertIn("evidence_conflicts", line)
        self.assertIn("quarantine", line)


if __name__ == "__main__":
    unittest.main()
