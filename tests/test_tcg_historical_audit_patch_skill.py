"""Check three TCG historical-audit skill mirrors and the routing/reporting contract."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
NAME = "tcg-historical-audit-patch-loop"


class HistoricalAuditPatchSkillTests(unittest.TestCase):
    def test_mirrors_and_metadata(self):
        contents = [(ROOT / folder / NAME / "SKILL.md").read_bytes()
                    for folder in (".agents/skills", ".codex/skills", ".github/skills")]
        self.assertEqual(contents[0], contents[1])
        self.assertEqual(contents[1], contents[2])
        self.assertIn("name: " + NAME, contents[0].decode("utf-8"))

    def test_both_routers_select_skill(self):
        for path in (".github/skills/tcg-skill-router/SKILL.md",
                     ".github/instructions/tcg-repository.instructions.md"):
            with self.subTest(path=path):
                self.assertIn(NAME, (ROOT / path).read_text(encoding="utf-8"))

    def test_two_phase_four_pass_and_safety(self):
        data = (ROOT / ".github/skills" / NAME / "SKILL.md").read_text(encoding="utf-8")
        for marker in ("PHASE A / AUDIT / READ-ONLY", "PHASE B / PATCH",
                       "Issue #901", "[AUDIT_HANDOFF]", "[PATCH_RESULT]",
                       "[CYCLE_LEDGER]", "R0", "R1", "R2", "R3", "R4",
                       "W001-W100", "CodeQL", "DEVICE_UNVERIFIED",
                       "before -> after", "protected main", "UNVERIFIED_HISTORY"):
            with self.subTest(marker=marker):
                self.assertIn(marker, data)


if __name__ == "__main__":
    unittest.main()
