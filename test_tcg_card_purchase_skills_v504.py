# -*- coding: utf-8 -*-
"""Scope proof for project-owned card-context and purchase-evidence agent skills."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parent
SKILLS = ("tcg-card-context", "tcg-purchase-evidence")


class CardPurchaseSkillsV504(unittest.TestCase):
    def test_project_skills_are_exactly_mirrored_and_routed(self):
        router = (ROOT / ".github/skills/tcg-skill-router/SKILL.md").read_text(encoding="utf-8")
        instructions = (ROOT / ".github/instructions/tcg-repository.instructions.md").read_text(encoding="utf-8")
        for name in SKILLS:
            with self.subTest(skill=name):
                agent = (ROOT / ".agents/skills" / name / "SKILL.md").read_bytes()
                codex = (ROOT / ".codex/skills" / name / "SKILL.md").read_bytes()
                self.assertEqual(agent, codex)
                self.assertIn(f"name: {name}", agent.decode("utf-8"))
                self.assertIn(f"`{name}`", router)
                self.assertIn(f"`{name}`", instructions)

    def test_card_generation_fails_closed_without_set_evidence(self):
        skill = (ROOT / ".agents/skills/tcg-card-context/SKILL.md").read_text(encoding="utf-8")
        for expected in ("Exact verified card number", "Artwork similarity alone never",
                         "Never derive release year from copyright year alone", "NARUTO"):
            self.assertIn(expected, skill)

    def test_purchase_candidates_cannot_claim_stock_or_promote_watch(self):
        skill = (ROOT / ".agents/skills/tcg-purchase-evidence/SKILL.md").read_text(encoding="utf-8")
        for expected in ("WATCH games remain excluded", "inventory_verified=false",
                         "A map result proves a location candidate", "Never fabricate price"):
            self.assertIn(expected, skill)


if __name__ == "__main__":
    unittest.main()
